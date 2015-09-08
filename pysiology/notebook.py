import sys
import copy
import tornado
import time
# Ya, I know, it's deprecated, but where are the actual imports??
import IPython
from IPython.html import widgets
from IPython.display import display
import pandas as pd
import bokeh
import nb_assets
import os
from tornado.websocket import websocket_connect
from tornado.httpclient import HTTPRequest
from pysiology.utils import message
import json
import zmq
from ipykernel.comm import Comm


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

    def start(self, websocket):
        """ Start Device on server. Streaming will start once the device is connected. If it is already,
            operational, streaming will commence immediately.
        """
        websocket.write_message(message(command=self.connect_command, address=self.address))
        websocket.write_message(message(command=self.start_command, address=self.address, interval=self.interval))

    def parse_message(self, msg):
        for key in self.streaming_keys:
            if key in msg:
                times, values = msg[key]
                new_ts = pd.TimeSeries(values, index=pd.to_datetime(times, unit="s"))
                if not hasattr(self, key):
                    setattr(self, key, new_ts)
                else:
                    old_ts = getattr(self, key)
                    setattr(self, key, old_ts.append(new_ts))

class Mindwave(Device):
    connect_command = "mindwave_connect"
    start_command = "mindwave_stream"
    streaming_keys = ["attention", "meditation", "poor_signal", "raw", "blink_strength"]

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
            device.start(self.websocket)
    def handler(self, msg):
        message = json.loads(msg)
        self.experiment.on_message(message)


class Experiment(object, metaclass=ExperimentMetaclass):
    def __init__(self):
        super().__init__()
        self.address_to_device = {}
        for name, device in self._devices.items():
            device = copy.deepcopy(device)
            setattr(self, name, device)
            self.address_to_device[device.address] = device

        self.server = ExperimentClient(self)
        self.stop_button = widgets.Button(description="Stop")

    def run(self):
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
                device.parse_message(msg)
        self.handler(self, msg)

    def __call__(self,handler):
        """ Experiment Classes can be used as a decorator, immeditiately running the Experiment
            and using the wrapped method as callback. """
        self.handler = handler
        self.run()


# Global for now...
update_bokeh_comm = None


def install_javascript():
    global update_bokeh_comm
    assets = [("coffeescript", "bokeh_update.coffee"),
            ]
    path = os.path.dirname(os.path.abspath(__file__))
    nb_assets.display_assets(assets, input_dir=os.path.join(path,"assets"), output_dir=os.path.join("static"))
    open_bokeh_comm()



def open_bokeh_comm():
    global update_bokeh_comm
    update_bokeh_comm = Comm(target_name='bokeh_update_target',
            target_module='pysiology', data={'some': 'data'})
def replace_bokeh_data_source(ds):
    update_bokeh_comm.send({"custom_type": "replace_bokeh_data_source",
            "ds_id": ds.ref['id'], # Model Id
            "ds_model": ds.ref['type'], # Collection Type
            "ds_json": bokeh.protocol.serialize_json(ds.vm_serialize())
    })

