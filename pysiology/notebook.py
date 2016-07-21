import sys
import json
import datetime
import copy
import re
import tornado
import time
import IPython
import os
from ipywidgets import widgets
from IPython.display import display
import pandas as pd
import numpy as np
from tornado.websocket import websocket_connect
from tornado.httpclient import HTTPRequest
from pysiology.utils import message
import tables
import h5py


class PysiologyClient(object):
    def __init__(self):
        self.websocket = None
        self.connected = None

    def __call__(self,handler):
        self.handler = handler
        self.run()

    def on_connected(self, fut):
        self.websocket = fut.result()
        #self.websocket.close()

    def run(self):
        request = HTTPRequest("ws://localhost:9010")
        self.connected = websocket_connect(request, on_message_callback=self.on_message)
        self.connected.add_done_callback(self.on_connected)

    def on_message(self, msg):
        if msg is not None:
            self.handler(msg)
        sys.stdout.flush()

    def stop(self):
        self.websocket.close()


class BluetoothDiscovery(PysiologyClient):
    def __init__(self):
        super().__init__()
    def on_connected(self, fut):
        super().on_connected(fut)
        self.websocket.write_message(message(command="discover_bluetooth"))
        sys.stdout.flush()
        tornado.ioloop.IOLoop.current().add_timeout(time.time()+15.0,callback=self.stop)
    def run(self):
        super().run()
    def stop(self):
        self.websocket.close()
        print("Discovery ended")
        sys.stdout.flush()
    def handler(self, msg):
        data = json.loads(msg)
        if 'mtp' in data:
            if data['mtp'] == "bluetooth_device_discovered":
                print(data['name'], " ", data['address'])



class Device(object):
    def __init__(self, address, interval=1.0):
        self.address = address
        self.interval = interval
    def __copy__(self):
        return self.__class__(self.address, self.interval)

    def start(self, experiment):
        """ Start Device on server. Streaming will start once the device is connected. If it is already,
            operational, streaming will commence immediately.
        """
        experiment.server.websocket.write_message(message(command=self.connect_command, address=self.address))
        experiment.server.websocket.write_message(message(command=self.start_command, address=self.address, interval=self.interval))

    def parse_message(self, experiment, msg):
        for key in self.streaming_keys:
            if key in msg:
                times, values = msg[key]
                times = np.array(times, dtype="float64")*1e9
                new_ts = pd.Series(values, index=pd.to_datetime(times, unit="ns"))
                experiment.data_logger.save(self.device_name, key, new_ts)
                if not hasattr(self, key):
                    setattr(self, key, new_ts)
                else:
                    old_ts = getattr(self, key)
                    setattr(self, key, old_ts.append(new_ts))


class Mindwave(Device):
    device_name = "mindwave"
    connect_command = "mindwave_connect"
    start_command = "mindwave_stream"
    streaming_keys = ["attention", "meditation", "poor_signal", "raw", "blink_strength"]


class Muse(Device):
    device_name = "muse"
    connect_command = "muse_connect"
    start_command = "muse_stream"
    streaming_keys = ["LAUX", "TP9", "AF7", "AF8", "TP10", "RAUX"]


class ExperimentMetaclass(type):
    def __init__(cls, name, bases, nmspc):
        if not hasattr(cls, "_devices"):
            cls._devices = {}
        else:
            cls._devices = cls._devices.copy()
        for k,v in nmspc.items():
            if isinstance(v, Device):
                cls._devices[k] = v
        super().__init__(name, bases, nmspc)


class ExperimentClient(PysiologyClient):
    def __init__(self, experiment):
        self.experiment = experiment
        super().__init__()

    def on_connected(self, fut):
        super().on_connected(fut)
        for name, device in self.experiment._devices.items():
            device.start(self.experiment)

    def handler(self, msg):
        message = json.loads(msg)
        self.experiment.on_message(message)


class Experiment(object, metaclass=ExperimentMetaclass):
    def __init__(self, file_name=None, max_rate=5):
        super().__init__()
        self.address_to_device = {}
        self.max_rate=max_rate
        self.last_message_time = time.time()
        for name, device in self._devices.items():
            device = copy.deepcopy(device)
            setattr(self, name, device)
            self.address_to_device[device.address] = device
        self.file_name = file_name


    def run(self):
        self.server = ExperimentClient(self)
        self.stop_button = widgets.Button(description="Stop")

        self.data_logger = DataLogger(self.file_name)
        IPython.display.display(self.stop_button)
        self.stop_button.on_click(self.on_stop_button_click)
        self.server.run()


    def on_stop_button_click(self, button):
        print("Stopped.")
        self.server.websocket.close()

    def on_message(self, msg):
        if "address" in msg:
            address = msg["address"]
            if address in self.address_to_device:
                device = self.address_to_device[address]
                device.parse_message(self, msg)
        if self.last_message_time < time.time()- 1.0 / self.max_rate:
            t = time.time()
            self.handler(self, msg)
            self.last_message_time = time.time()


    def __call__(self,handler):
        """ Experiment Classes can be used as a decorator, immeditiately running the Experiment
            and using the wrapped method as callback. """
        self.handler = handler
        self.run()


class DataLogger(object):
    """ Encapsulates the logging of TimeSeries data to an HDF5 file,
        mainly to keep the Experiment class from becoming too verbose and
        confusing.
    """
    def __init__(self, file_name):
        self.file_name = file_name
        self.run = 1
        if self.file_name is not None:
            hf = tables.open_file(self.file_name, "a")
            try:
                while hf.get_node("/run_%i" % self.run):
                    self.run += 1
            except tables.NoSuchNodeError:
                pass
            hf.close()

    def save(self, prefix, key, ts):
        if self.file_name:
            path = "run_%i/%s/%s" % (self.run, prefix, key)
            ts.to_hdf(self.file_name, path, append=True)

    def log_single_value(self, key, value):
        if self.file_name:
            path = "run_%i/experiment/%s" % (self.run, key)
            ts = pd.Series([value], index=[datetime.datetime.now()])
            ts.to_hdf(self.file_name, path, append=True)



"""
    # Analysis of recorded experiments
    Should probably be factored out into seperate library, but is currently too tightly bound
    to HDF5 file format.

"""

class AnalysisRun(object):
    def __init__(self, run_number):
        self.run_number = run_number
        self.devices = {}
        
    def add_device(self, device):
        self.devices[device.name] = device
    
    
    def iterate_timeseries(self):
        for device_name,device in self.devices.items():
            for name, ts in device.data.items():
                yield ts
    
    def get_span(self):
        earliest = None
        latest = None
        for ts in self.iterate_timeseries():
            start_time = ts.index[0]
            end_time = ts.index[-1]
            if latest is None or latest<end_time:
                latest = end_time

            if earliest is None or earliest > start_time:
                earliest = start_time
        return earliest,latest
        
class AnalysisDevice(object):
    def __init__(self, device_name):
        self.name = device_name
        self.data = {}
    def add_data(self, name, ts):
        self.data[name] = ts
        
class Analysis(object):
    """ Opens an HDF5 File created by logging Experiments."""
    def __init__(self, filename):
        self.file = h5py.File(filename, "r")
        self.runs = {}
        self.parse_structure()

    def find_runs(self):
        for node_name in list(self.file):
            try:
                number =  int(re.match(r"run_(\d+)", node_name).groups()[0])
            except IndexError:
                continue
            yield number, self.file[node_name]
            
    def parse_structure(self):
        for run_number, run_node in self.find_runs():
            run = AnalysisRun(run_number)
            self.runs[run_number] = run
            for device_name in list(run_node):
                device = AnalysisDevice(device_name)
                run.add_device(device)
                for name in list(run_node[device_name]):
                    df = self.make_timeseries(name, run_node[device_name][name])
                    device.add_data(name, df)

    def make_timeseries(self, name, node):
        df = pd.DataFrame.from_records(node["table"][:])
        t = df['index'].astype(np.float64)
        
        df.index = pd.to_datetime(t, unit="ns")
        del df['index']
        df.columns = [name]
        ts = df.ix[:,0]
        ts.name = name
        return ts.sort_index()
    
    def iterate_timeseries(self):
        for i,run in self.runs.items():
            for device_name,device in run.devices.items():
                for name, ts in device.data.items():
                    yield df

    def iterate_windows(self, window_size, step_size=None):
        global test, w_start, w_end
        latest = datetime.datetime.fromtimestamp(0)
        earliest = None
        second = pd.Timedelta("1s")
        for run_number, run in self.runs.items():
            start_time, end_time = run.get_span()
            duration = (end_time - start_time).seconds
            for i in range(0, duration, step_size):
                w_start = start_time + second*i
                w_end = w_start + second*window_size
                window = dict(start=w_start,
                              end=w_end,
                              run=run,
                              run_number=run_number
                              )
                for device_name, device in run.devices.items():
                    d = dict()
                    for name, ts in device.data.items():
                        sub = ts[w_start:w_end]
                        bound = ts.index.get_slice_bound(w_start, "left", "loc")
                        last_ = ts[bound:bound+1]
                        sub = pd.concat((last_, sub))
                        d[name] = sub
                    window[device_name] = d        
                yield window
