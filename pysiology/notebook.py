import pandas as pd
import json
import re
import IPython
from IPython.core import display
from IPython.html import widgets
from IPython.html.widgets import interact
from IPython.utils.traitlets import Unicode, Bool
import bokeh
from bokeh.plotting import *
from bokeh.protocol import serialize_json
import asyncio
from asyncio import coroutine, sleep, async, wait
import os
import aiohttp
import numpy as np
import sys
import bokeh
import nb_assets
import zmq
import h5py
from pysiology.pyeeg import bin_power


def install_asyncio_loop():
    zmq_loop = zmq.eventloop.ioloop.IOLoop.instance()
    loop = asyncio.get_event_loop()

    def callback():
        loop.call_later(0.02, dummy)
        loop._run_once()
        cb.start()
        ipython = IPython.get_ipython()
        ipython.kernel.do_one_iteration()
    cb = zmq.eventloop.ioloop.DelayedCallback(callback, 0.05)
    cb.start()

def install_javascript():
    assets = [("coffeescript", "asyncio_task_widget.coffee"),
            ]
    path = os.path.dirname(os.path.abspath(__file__))
    nb_assets.display_assets(assets, input_dir=os.path.join(path,"assets"), output_dir=os.path.join("static"))

def dummy():
    pass


class AsyncioTaskWidget(widgets.DOMWidget):
    _view_module = Unicode('asyncio', sync=True)
    _view_name = Unicode('AsyncioTaskWidgetView', sync=True)
    def __init__(self, task, *args, **kwargs):
        widgets.DOMWidget.__init__(self, *args, **kwargs)
        loop = asyncio.get_event_loop()
        self.task = loop.create_task(task)
        self.task.add_done_callback(self.finish_task_callback)
        self.on_msg(self._handle_custom_msg)

    def _handle_custom_msg(self, msg):
        msg_type = msg['msg_type']
        if msg_type == 'stop_task':
            self.task.cancel()

    def finish_task_callback(self, fut):
        self.send(dict(msg_type="task_stopped"))

class Message(object):
    def __init__(self, data):
        pass

value_names = ["attention", "meditation", "poor_signal", "blink_strength", "raw"]
class MindwaveMessage(Message):
    def __init__(self, data):
        for name in value_names:
            times, values = data[name]
            ts = pd.TimeSeries(values, index=pd.to_datetime(times, unit="s"),
                               dtype=np.int16)
            setattr(self, name, ts)


class Experiment(object):
    mindwave_value_names = value_names
    def __init__(self, file_name=None):
        self.widget = None

        self.websocket = None
        self.ws_task = None
        for name in self.mindwave_value_names:
            setattr(self, name,  None)

        self.file_name = file_name
        if file_name is not None:
            self.batch_number = self.get_free_batch(self.file_name)
        else:
            self.batch_number = 0

    def __call__(self, handler):
        self.handler = handler
        self.execute()

    def parse_message(self, text):
        data = json.loads(text)
        message = None
        if data['mtp'] == 'mindwave-stream':
            message = MindwaveMessage(data)
            for name in value_names:
                new_data = getattr(message, name)
                old_data = getattr(self, name)
                if len(new_data)>0:
                    if old_data is None:
                        setattr(self, name, new_data.copy())
                    else:
                        setattr(self, name, pd.concat([old_data, new_data]))

        if message is not None:
            self.handler(self, message)
            if self.file_name is not None:
                self.save()
        sys.stdout.flush()

    @coroutine
    def run(self):
        loop = asyncio.get_event_loop()
        self.ws_task = loop.create_task(self.websocket_receive())
        while 1:
            yield from sleep(0.05)


    def execute(self):
        self.widget = AsyncioTaskWidget(self.run())
        self.widget.task.add_done_callback(self.finish)
        display.display(self.widget)

    def finish(self, fut):
        loop = asyncio.get_event_loop()
        self.ws_task.cancel()

        if self.websocket is not None:
            loop.create_task(self.websocket.close())

        if self.file_name is not None:
            self.save()
    @coroutine
    def websocket_receive(self):
        i = 0
        while True:
            try:
                print("connecting ...")
                self.websocket = yield from aiohttp.websocket_client.ws_connect("http://127.0.0.1:9010/")
            except aiohttp.errors.ClientOSError:
                print ("no connection possible")
                yield from sleep(5)
                continue
            yield from sleep(0.5)
            while True:
                i += 1
                msg = yield from self.websocket.receive()
                if msg.tp == aiohttp.MsgType.text:
                    self.parse_message(msg.data)
                elif msg.tp == aiohttp.MsgType.closed:
                    print("closing")
                    yield from sleep(5)
                    break
                elif msg.tp == aiohttp.MsgType.error:
                    print("Error")
                    yield from sleep(5)
                    break

    def get_free_batch(self, file_name):
        f = h5py.File(file_name)
        def int_or_minus_one(x):
            try:
                return int(x)
            except:
                return -1
        cands = list([int_or_minus_one(re.match(r"pysiology_batch_(\d+)", k).groups()[0]) for k in f.keys()])
        if len(cands)>0:
            highest=max(cands)
        else:
            highest = -1
        return highest+1

    def save_batch(self, file_name, batch_number=0, ):
        group_name = "pysiology_batch_%i" % batch_number
        f = h5py.File(file_name)

        try:
            group = f[group_name]
        except KeyError:
            group = f.create_group(group_name)
        for name in ["attention", "meditation", "poor_signal", "blink_strength", "raw"]:
            ts = getattr(self, name)
            if ts is None:
                continue
            try:
                del group[name]
            except:
                pass
            ts_group = group.create_group(name)
            try:
                del ts_group["times"]
            except:
                pass
            try:
                del ts_group["values"]
            except:
                pass

            times = ts.index.values.astype("float64")/ 1e9
            times_ds = ts_group.create_dataset("times", (len(ts),), data=times);
            values_ds = ts_group.create_dataset("values", (len(ts),), data=ts.values)
        f.close()

    def save(self):
        self.save_batch(self.file_name, self.batch_number)

class BokehAnimationWidget(widgets.DOMWidget):
    _view_module = Unicode('asyncio', sync=True)
    _view_name = Unicode('BokehAnimationWidget', sync=True)
    value = Unicode(sync=True)

    def __init__(self, *args, **kwargs):
        widgets.DOMWidget.__init__(self,*args, **kwargs)
        self.iteration = 0
        self.on_msg(self._handle_custom_msg)
        self.stopped = False

    def replace_bokeh_data_source(self, ds):
        self.send({"custom_type": "replace_bokeh_data_source",
                "ds_id": ds.ref['id'], # Model Id
                "ds_model":ds.ref['type'], # Collection Type
                "ds_json": bokeh.protocol.serialize_json(ds.vm_serialize())
        })
    def start(self):
        self.iteration = 0
        self.stopped = False

    def _handle_custom_msg(self, content):
        if content['msg_type']=='stop':
            self.stopped = True

    def running(self):
        self.iteration +=1
        get_ipython().kernel.do_one_iteration()
        return not self.stopped

def bokeh_animation_widget():
    w = BokehAnimationWidget()
    display.display(w)
    return w


class Batch(object):
    """ "Resurrects" a recorded experiment.
    """
    names = ["meditation", "attention", "raw", "poor_signal", "blink_strength"]
    def __init__(self, file_name, batch=None):
        file = h5py.File(file_name)
        self.file_name = file_name
        self.batch = batch
        if batch is None:
            for batch in range(10):
                try:
                    file['pysiology_batch_%i' % (batch+1)]
                except:
                    break
        batch_group_name = 'pysiology_batch_%i' % batch
        for name in self.names:
            if not name in file[batch_group_name]:
                continue
            times = np.array(file[batch_group_name][name]['times'], dtype=np.float64)
            ts = pd.TimeSeries(file[batch_group_name][name]['values'], index=pd.to_datetime(times, unit="s"))
            setattr(self, name, ts)
        file.close()

    def windowed(self, freq="1S", left_offset=1, right_offset=0):
        """ Iterates over windows in the dataset. """
        start = min([getattr(self, name).index[0] for name in self.names if name in self.__dict__])
        end = max([getattr(self, name).index[-1] for name in self.names if name in self.__dict__])
        anchors = pd.date_range(start, end, freq=freq)

        for i, anchor in enumerate(anchors):
            right = anchor+right_offset
            left = right - pd.to_timedelta("%is"%left_offset)

            meta = dict(anchor=anchor,
                     left=left,
                     right=right,
                     index="%s#%i#%i" % (self.file_name, self.batch, i),
                    )
            data = dict()

            for name in self.names:
                try:
                    ts = getattr(self, name)
                except AttributeError:
                    data[name] = None
                    continue
                tindex = ts.index
                window =  ts[(tindex>=left)&(tindex<=right)]
                data[name] = window
            yield dict(meta), dict(data)

    def to_data_frame(self):
        """ Returns a tabularized dataset """
        freqs = np.arange(1,35)
        bin_names = ["bin_%i" % i for i in freqs]
        self.bin_names = bin_names
        dicts = []
        indices = []
        def nansafe(x, default=0):
            if np.isnan(x):
                return default
            else:
                return x

        for meta, data in self.windowed("250L"):
            indices.append(meta['index'])
            raw = data['raw']
            meta["raw_length"] = len(raw)
            if len(raw) >= 512:
                absbins, relbins = bin_power(raw.values, freqs, 512)
                for bin_name, strength in zip(bin_names, relbins):
                    meta[bin_name] = strength

            poor = nansafe(data['poor_signal'].max())
            meta["poor_signal"] = poor
            meta["attention"] = nansafe(data['attention'].mean())
            meta["meditation"] = nansafe(data['meditation'].mean())
            meta["raw_sd"] = nansafe(data['raw'].std())
            dicts.append(meta)
        return pd.DataFrame.from_records(dicts, index="index")
