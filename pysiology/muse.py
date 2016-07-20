import time
from collections import defaultdict
import asyncio
from asyncio import coroutine, sleep, async
import bluetooth
import numpy as np
import bcolz
from sample_source import SampleSource
from utils import TSLogger, message
from streamer import StreamerCommand
import json
from command import ServerCommand
import muse_parser




class MuseManager(object):
    """ Manages the Muse devices globally. Not tested with multiple devices yet,
        though. """

    def __init__(self):
        self.devices = {}

    def connect(self, address):
        if address in self.devices:
            return self.devices[address].connected.wait()
        device = MuseDevice(address)
        self.devices[address] = device
        asyncio.get_event_loop().create_task(device.run())
        return device.connected.wait()

    def disconnect(self, address):
        self.devices[address].disconnect()

muse_manager = MuseManager()

class MuseDeviceParser(muse_parser.Parser):
    def __init__(self, device):
        self.device = device
        super().__init__()
    def receive_value(self, channel, value):
        self.device.receive_value(channel, value)


class MuseDevice(object):
    channel_names = ["TP9", "AF7", "AF8", "TP10", "LAUX", "RAUX", "battery_percent"]
    def __init__(self, addr):
        super().__init__()
        self.addr = addr
        self.record = True
        self.sample_count = 0
        self.time_offset = None
        self.loggers = {}
        for channel in self.channel_names:
            logger = TSLogger(dtype="int16")
            self.loggers[channel] = logger
            logger.timing_counter = 0 
        self.connected = asyncio.Event()

    def get_indices(self):
        return

    @coroutine
    def run(self):
        yield from self.connect()

    @coroutine
    def receive_short(self):
        for i in range(10):
            yield from sleep(0.1)
            try:
                line = self.socket.recv(1000)
                return line
            except:
                continue
        return b""


    @coroutine
    def try_to_connect(self):
        try:
            self.socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            self.socket.connect((self.addr, 1))
            self.socket.setblocking(False)
        except bluetooth.BluetoothError as e:
            print(e)
            return False
        # Get hardware/firmware versions,
        # useful for debugging with new devices
        yield from sleep(0.1)
        self.socket.send("v\n")
        line = yield from self.receive_short()
        if line is None:
            return False
        print(line.decode("ascii"))
        
        # Preset AB for research mode, 500hz, 16bit
        self.socket.send("%AB\n")
        yield from sleep(0.1)
        # Select 50hz notch filter
        self.socket.send("g 408c\n")
        yield from sleep(0.05)
        self.socket.send("?\n")
        line = yield from self.receive_short()
        if line is None:
            return False
        print(line.decode("ascii"))
        return True

    @coroutine
    def connect(self):
        while 1:
            self.sample_count = 0
            print("Trying to connect")
            # Loop until a connection is successful
            success = yield from self.try_to_connect()
            if success:
                print("Connection made!")
                self.connected.set()
                yield from self.read_loop()
            else:
                print("Connecting to Muse failed")
                yield from sleep(3)


    @coroutine
    def read_loop(self):
        """ Reads repeatedly from bluetooth socket, and returns if errors are
            deemed unrecoverable. """
        error_count = 0
        parser = MuseDeviceParser(self)
        self.socket.send("s\n")
        self.time_offset = time.time()
        self.next_keepalive = time.time() + 5
        for channel in self.channel_names:
            self.loggers[channel].timing_counter = 0 
        while 1:
            if not self.record:
                yield from sleep(1)
                continue

            yield from sleep(0.05)
            if self.next_keepalive < time.time():
                self.next_keepalive = time.time()+5
                self.socket.send("k\n")
            try:
                buffer = self.socket.recv(10000)
                for b in buffer:
                    parser.send(b)
                error_count = 0

            except bluetooth.BluetoothError as e:
                # Errno 11 is thrown quite often, and usually
                # only means that no new data has been sent.
                if str(e).startswith("(11"):
                    error_count += 1
                    if error_count > 5:
                        self.socket.close()
                        return
                    yield from sleep(0.025)
                else:
                    print("error on reading:", e)
                    self.socket.close()
                    yield from sleep(1)
                    return

    def receive_value(self, channel, value):
        # Muse doesn't send any timing information, so we assume
        # constant frequencies which is 500 for EEG and 50 for Accel.
        # Battery data is a lot more rare so we get the current time.
        logger = self.loggers[channel]
        if channel == "battery_percent":
            t = time.time()
        elif channel in ["ACCEL1", "ACCEL2"]:
            t =  self.time_offset + (logger.timing_counter / 50.0)
            logger.timing_counter += 1
        else:
            t =  self.time_offset + (logger.timing_counter / 500.0)
            logger.timing_counter += 1
        logger.log(t, value)

    def disconnect(self):
        pass
    def get_indices(self):
        return {k:len(v) for k,v in self.loggers.items()}


class MuseConnectCommand(ServerCommand):
    @coroutine
    def run(self, **kwargs):
        print ("Connecting to Muse...")
        address = kwargs['address']
        print(address)
        yield from muse_manager.connect(address)
        yield from self.websocket.send(message(msg="muse_connected"))


class MuseStreamCommand(StreamerCommand):
    @coroutine
    def run(self, address=None, interval=1.0, **kwargs):
        device = muse_manager.devices[address]
        msg = dict(mtp="muse_status",
                       address=address,
                       status="connecting",
                       )

        yield from device.connected.wait()

        print ("Start streaming")
        time_start = time.time()
        last_indices = device.get_indices()
        while not self.cancelled:
            yield from sleep(0.2)
            msg = dict(mtp="muse_stream",
                       address=address)
            for key,ts in device.loggers.items():
                last_index = last_indices[key]
                times = ts.times[last_index:]
                values = ts.values[last_index:]
                if len(values)>0:
                    msg[key] = [times, values]
            last_indices = device.get_indices()
            json = message(**msg)
            yield from self.websocket.send(json)
