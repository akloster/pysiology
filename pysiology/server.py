import asyncio
from asyncio import coroutine, sleep, async, wait
import aiohttp
import bluetooth
from aiohttp import web
import time
from bitalino import BitalinoManager, BitalinoPeriodicStreamer
from sample_source import SampleSource
import json
from np_json import ArrayAwareJSONEncoder
import numpy as np
from mindwave import MindwaveManager, MindwaveStreamer
from utils import fork


class PysioWebSocket(object):
    def __init__(self, server):
        self.server = server
        self.message_queue = asyncio.Queue()
    @coroutine
    def sender(self, ws):
        while True:
            msg_text = yield from self.message_queue.get()
            ws.send_str(msg_text)

    @coroutine
    def __call__(self, request, *args, **kwargs):
        ws = web.WebSocketResponse()
        ws.start(request)

        """streamer = BitalinoPeriodicStreamer(bitalino_manager=self.server.sample_sources[0],
                                    channel=1,
                                    interval=1,
                                    stretch=5.0
                                    )"""

        streamer = MindwaveStreamer(mindwave_manager=self.server.sample_sources[0],
                                    interval=0.1)

        streamer_task = fork(streamer.run(self.message_queue))
        sender_task = fork(self.sender(ws))
        print("Starting Socket output")
        while True:
            msg = yield from ws.receive()
            if msg.tp == aiohttp.MsgType.close:
                print("Websocket closed")
                break
            elif msg.tp == aiohttp.MsgType.error:
                print("Websocket error: ", ws.exception())
                break
        streamer_task.cancel()
        sender_task.cancel()
        return ws


    @classmethod
    def as_view(cls, server):
        return PysioWebSocket(server)

class DataServer(web.Application):
    def __init__(self):
        super().__init__()
        self.sample_sources = []
        self.router.add_route('GET', '/', PysioWebSocket.as_view(self))

    @coroutine
    def run(self):
        self.bluetooth_manager = BluetoothManager(start_discovery=False)
        yield from async(self.bluetooth_manager.run())

        while 1:
            for source in self.sample_sources:
                pass
            yield from sleep(2)


    def add_source(self, source):
        self.sample_sources.append(source)
        loop = asyncio.get_event_loop()
        loop.create_task(source.run())



class AsyncDiscoverer(bluetooth.DeviceDiscoverer):
    """ This is pybluez' attempt at customizing the discovery process.
        This class contains callbacks for various parts of the process.
        However, the documentation doesn't exactly tell you that you need
        to call BluetoothDiscoverer.process_event() explicitly!
    """
    def device_discovered(self, address, device_class, name, sth):
        # put events into an asyncio Queue
        self.queue.put_nowait((address,  device_class, name, sth))

    def pre_inquiry(self):
        self.done = False

    def inquiry_complete(self):
        self.done = True


class BluetoothManager(object):
    def __init__(self, start_discovery=True):
        self.addresses = []
        self.start_discovery = start_discovery
        self.device_events = asyncio.Queue()
        self.devices_seen_last = {}
        self.name_cache = {}

    @coroutine
    def run(self):
        if self.start_discovery:
            async(self.discovery())
            while 1:
                event = yield from self.device_events.get()
                addr = event[0]
                self.devices_seen_last[addr] = time.time()
                if not addr in self.name_cache:
                    try:
                        print("Name lookup...")
                        name =  bluetooth.lookup_name(addr, timeout=10)
                        self.name_cache[addr] = name
                        print(addr, name)
                        if name == "bitalino":
                            print("Found bitalino!")
                            bitalino = BitalinoManager(addr)
                            asyncio.get_event_loop().create_task (bitalino.run())
                    except:
                        continue
                else:
                    pass

    @coroutine
    def discovery(self):
        while 1:
            print("Looking for devices")
            try:
                bd = AsyncDiscoverer()
                bd.queue = self.device_events
                bd.find_devices(lookup_names=False, duration=8)
            except bluetooth.BluetoothError:
                # An exception at this stage is a very bad sign. Probably no BT adapter
                # is available.
                print("Error encountered while scanning for bluetooth devices.")
            while 1:
                try:
                    bd.process_event()
                except bluetooth._bluetooth.error as e:
                    # May happen when discovery is already complete
                    pass
                except TypeError as e:
                    print(e)
                if bd.done:
                    break
                yield from sleep(0.1)

            yield from sleep(2)



@coroutine
def test2():
    i = 0
    while 1:
        i =i+1
        t = time.time()
        yield from sleep(1)
        print("%i %.2f " % (i, time.time()-t))


@coroutine
def wstest():
    print("Wstest")
    i = 0
    ws = yield from aiohttp.websocket_client.ws_connect("127.0.0.1:9010/")
    yield from sleep(0.5)
    while 1:
        i += 1
        data = yield from ws.receive()
        print(data)


@coroutine
def test():
    yield from async(test2())
    print("finished")

loop = asyncio.get_event_loop()

#bluetooth_manager = BluetoothManager()
#loop.create_task(bluetooth_manager.run())
app = DataServer()
mindwave = MindwaveManager("74:E5:43:BE:42:50")
app.add_source(mindwave)
#addr = "98:D3:31:40:1B:B0"
#bitalino = BitalinoManager(addr)
#app.add_source(bitalino)
f = loop.create_server(app.make_handler(), '127.0.0.1', 9010)
loop.create_task(app.run())
loop.create_task(f)

try:
    loop.run_until_complete(test())
except KeyboardInterrupt:
    pass

