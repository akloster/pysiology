"""
	Mindwave Driver
"""
import asyncio
from asyncio import coroutine, sleep, async
import bluetooth
import time
import numpy as np
import bcolz
from sample_source import SampleSource
from utils import TSLogger, message
from streamer import StreamerCommand
import json
from command import ServerCommand


class MindwaveConnectCommand(ServerCommand):
    @coroutine
    def run(self, **kwargs):
        print ("Connecting to Mindwave")
        address = kwargs['address']
        yield from mindwave_manager.connect(address)
        yield from self.websocket.send(message(msg="mindwave_connected"))


class MindwaveManager(object):
    """ Manages the Mindwave devices globally. Not tested with multiple devices yet,
        though. """

    def __init__(self):
        self.devices = {}

    def connect(self, address):
        """ Connects the server to  thedevice with the given address.
            Returns: A Task which finishes when the connection is successful.
            This is not a coroutine, even though it returns a Task.
        """
        if address in self.devices:
            return self.devices[address].connected.wait()
        device = MindwaveDevice(address)
        self.devices[address] = device
        asyncio.get_event_loop().create_task(device.run())
        return device.connected.wait()

    def disconnect(self, address):
        self.devices[address].disconnect()


mindwave_manager = MindwaveManager()

class MindwaveDevice(object):
    def __init__(self, addr):
        super().__init__()
        self.addr = addr
        self.record = True
        self.sample_count = 0
        self.time_offset = None

        self.segments = []

        self.raw = TSLogger(dtype="float16")
        self.attention = TSLogger()
        self.meditation = TSLogger()
        self.poor_signal = TSLogger()
        self.blink_strength = TSLogger()
        self.connected = asyncio.Event()


    def get_indices(self):
        return dict(raw=len(self.raw),
                attention=len(self.attention),
                meditation=len(self.meditation),
                poor_signal=len(self.poor_signal),
                blink_strength=len(self.blink_strength),
            )

    @coroutine
    def run(self):
        yield from self.connect()

    @coroutine
    def try_to_connect(self):
        try:
            self.socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            self.socket.connect((self.addr, 1))
            self.socket.setblocking(False)
        except bluetooth.BluetoothError as e:
            print(e)
            return False
        return True

    @coroutine
    def connect(self):
        """ Try to connect to the device. This coroutine runs forever. """
        while 1:
            #self.channel_samples = [bcolz.carray([]) for i in range(n)]
            self.sample_count = 0
            print("Trying to connect")
            # Loop until a connection is successful

            success = yield from self.try_to_connect()
            if success:
                print("Connection made!")
                self.connected.set()
                #self.segments.append(self.channel_samples)
                yield from self.read_loop()
            else:
                yield from sleep(3)



    @coroutine
    def read_loop(self):
        """ Reads repeatedly from bluetooth socket, and returns if errors are
            deemed unrecoverable. """
        parser = self.parser()
        next(parser)
        error_count = 0
        self.time_offset = time.time()
        while 1:
            if self.record:
                yield from sleep(0.05)
                try:
                    buffer = self.socket.recv(3000)
                    self.raw_counter = 0
                    for b in buffer:
                        parser.send(b)
                    self.time_offset = time.time()
                    error_count = 0

                except bluetooth.BluetoothError as e:
                    print("error on reading:", e)
                    if str(e) == "(11, 'Resource temporarily unavailable')":
                        error_count += 1
                        if error_count > 3:
                            self.socket.close()
                            return
                        yield from sleep(0.01 + error_count*0.01)
                    else:
                        self.socket.close()
                        yield from sleep(0.5)
                        return
            else:
                yield from sleep(0.5)

    def parser(self):
        packet = np.zeros(170, dtype=np.uint8)
        while 1:
            byte = yield
            if byte != 0xaa:
                continue
            byte = yield
            if byte !=0xaa:
                continue
            packet_length = -1
            try:
                while 1:
                    packet_length = yield
                    if packet_length == 0xaa:
                        continue
                    if packet_length > 170:
                        raise ValueError("PLENGTH TOO LARGE")
                    break
            except ValueError:
                continue
            for i in range(packet_length):
                b = yield
                packet[i] = b
            checksum = int(packet[:packet_length].sum()) & 0xff
            checksum = ~ checksum & 0xff
            tchecksum = yield
            if checksum != tchecksum:
                continue
            pos = 0
            while pos<packet_length:
                code = packet[pos]
                pos+=1
                if code == 0x02:
                    # poor
                    v = packet[pos]
                    #self.poor_signal.log()
                    self.poor_signal.log(self.time_offset, v)
                    pos += 1
                elif code == 0x04:
                    # attention
                    v = packet[pos]
                    self.attention.log(self.time_offset, v)
                    pos += 1
                elif code == 0x05:
                    # meditation
                    v = packet[pos]
                    self.meditation.log(self.time_offset, v)
                    pos +=1
                elif code == 0x16:
                    v = packet[pos]
                    self.blink_strength.log(self.time_offset, v)
                    pos +=1
                elif code == 0x80:

                    t = self.time_offset + self.raw_counter * 1/512.0
                    pos += 1
                    a, b = packet[pos:pos+2]
                    v = int(a)*256 + int(b)
                    if v > 32768:
                        v -=65536
                    self.raw.log(t,v)
                    self.raw_counter += 1
                    pos+=2
                elif code >= 0x80:
                    l = packet[pos]
                    pos += l+1
                else:
                    print(hex(code))
                    #pos +=1
            continue
    def disconnect(self):
        pass

value_names = ["attention", "meditation", "poor_signal", "blink_strength", "raw"]


class MindwaveStreamCommand(StreamerCommand):
    @coroutine
    def run(self, address=None, interval=1.0, **kwargs):
        if address not in mindwave_manager.devices:
            self.websocket.send(msg="mindwave_error",
                                error_name="address not connected",
                                description="No device with this address connected.")
            return
        device =  mindwave_manager.devices[address]

        last_index = 0
        print ("Mindwave Streaming")
        yield from device.connected.wait()
        last_indices = device.get_indices()
        last_indices = device.get_indices()
        while True:
            yield from device.connected.wait()
            yield from sleep(interval)
            msg = dict(mtp="mindwave_stream",
                       address=address)
            for name in value_names:
                ts = getattr(device, name)
                last_index = last_indices[name]
                values = ts.values[last_index:]
                times = ts.times[last_index:]
                #print (name, " ", len(values), " ", len(times))
                msg[name] = [times, values]

            last_indices = device.get_indices()
            yield from self.websocket.send(message(**msg))

