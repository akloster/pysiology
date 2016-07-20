import asyncio
from asyncio import coroutine, sleep, async, wait, gather
import aiohttp
import bluetooth
from aiohttp import web
import time
from bitalino import BitalinoManager, BitalinoConnectCommand, BitalinoStreamCommand
from sample_source import SampleSource
import json
from pysiology.np_json import ArrayAwareJSONEncoder
import numpy as np
from mindwave import MindwaveConnectCommand, MindwaveStreamCommand
from utils import fork, message, first_completed
from bluetooth_discovery import  DiscoverBluetoothCommand
from muse import MuseStreamCommand, MuseConnectCommand



command_mapping = {'discover_bluetooth': DiscoverBluetoothCommand,
                   'mindwave_connect': MindwaveConnectCommand,
                   'mindwave_stream': MindwaveStreamCommand,
                   'bitalino_connect': BitalinoConnectCommand,
                   'bitalino_stream': BitalinoStreamCommand,
                   'muse_stream': MuseStreamCommand,
                   'muse_connect': MuseConnectCommand,
                   }

class PysioWebSocket(object):
    def __init__(self, server):
        self.server = server
        self.message_queue = asyncio.Queue(maxsize=10)
        self.running_commands = []

    @coroutine
    def send(self, msg):
        yield from self.message_queue.put(msg)

    @coroutine
    def __call__(self, request, *args, **kwargs):
        ws = web.WebSocketResponse()
        ws.start(request)
        ws.send_str(message(mtp="HELLO"))
        stop = False
        while not stop:
            try:
                msgs = yield from first_completed(ws=ws.receive(),
                                          send=self.message_queue.get())
            except RuntimeError as e:
                print(e)
                break
            for name, msg in msgs:
                if name=="ws":
                    if msg.tp == aiohttp.MsgType.close:
                        print("Websocket closed")
                        break
                    elif msg.tp == aiohttp.MsgType.error:
                        print("Websocket error:")
                        break
                    else:
                        if msg.data is None:
                            print (msg)
                        else:
                            self.parse_message(msg.data)
                elif name=="send":
                    x = ws.send_str(msg)
        print("Cancelling tasks")

        for command in self.running_commands:
            try:
                command.cancel()
            except:
                pass
        return ws

    def parse_message(self, data):
        data = json.loads(data)
        try:
            command_class= command_mapping[data['command']]
        except KeyError:
            print ("unknown command %s" % data['command'])
            return

        command = command_class(self)
        command(**data)
        self.running_commands.append(command)

    @classmethod
    def as_view(cls, server):
        return cls(server)


class DataServer(web.Application):
    def __init__(self):
        super().__init__()
        self.sample_sources = []
        self.router.add_route('GET', '/', PysioWebSocket.as_view(self))

    @coroutine
    def run(self):
        while 1:
            for source in self.sample_sources:
                pass
            yield from sleep(2)

    def add_source(self, source):
        self.sample_sources.append(source)
        loop = asyncio.get_event_loop()
        task = loop.create_task(source.run())
        def temp():
            task.result()
        task.add_done_callback(temp)

loop = asyncio.get_event_loop()

#loop.create_task(bluetooth_manager.run())
#mindwave addr = MindwaveManager("74:E5:43:BE:42:50")
#bitalino addr = "98:D3:31:40:1B:B0"

app = DataServer()
f = loop.create_server(app.make_handler(), '127.0.0.1', 9010)
loop.create_task(f)
loop.create_task(app.run())

@coroutine
def test():
    i = 0
    while 1:
        i+=1
        print(i)
        yield from sleep(1)
#loop.create_task(test())
try:
    loop.run_forever()
except KeyboardInterrupt:
    pass

