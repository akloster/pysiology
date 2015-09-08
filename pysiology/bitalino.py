"""
	Currently defunct. Maybe after Europython ;-)

"""
import asyncio
from asyncio import coroutine, sleep, async
import bluetooth
import time
import math
import random
import numpy as np
import bcolz
from streamer import StreamerCommand
from utils import TSLogger, message
from command import ServerCommand


def packet_size(nChannels):
    if nChannels>4:
        return int(math.ceil((52.+6.*(nChannels-4))/8.))
    else:
        return int(math.ceil((12.+10.*(nChannels))/8.))


class BitalinoParserError(Exception):
    pass


class BitalinoConnectCommand(ServerCommand):
    @coroutine
    def run(self, **kwargs):
        print ("connect bitalino...")
        address = kwargs['address']
        print(address)
        yield from bitalino_manager.connect(address)
        yield from self.websocket.send(message(msg="bitalino_connected"))


class BitalinoManager(object):
    """ Manages the Bitalinodevices globally. This is very much
        the same as the MindwaveManager, but before I merge the two
        into some class hierarchy, I need to be more sure about how
        everything should fit together in the end.
        
        There are differences in managing bitalino and mindwave
        devices. The bitalino (or at least my implementation of
        the parser) sometimes messes up and the recording needs 
        to be restarted. The Mindwave's protocol on the other hand
        is rock solid. """

    def __init__(self):
        self.devices = {}

    def connect(self, address):
        """ Connects the server to  thedevice with the given address.
            Returns: A Task which finishes when the connection is successful.
            This is not a coroutine, even though it returns a Task.
        """
        if address in self.devices:
            return self.devices[address].connected.wait()

        device = BitalinoDevice(address)
        self.devices[address] = device
        asyncio.get_event_loop().create_task(device.run())
        return device.connected.wait()

    def disconnect(self, address):
        self.devices[address].disconnect()


bitalino_manager = BitalinoManager()


class BitalinoDevice(object):
    def __init__(self, addr):
        super().__init__()
        self.addr = addr
        self.analog_channels = (1, 2, 3)
        self.rate = 1000

        self.time_offset = None
        n = len(self.analog_channels)
        self.connected = asyncio.Event()

    @coroutine
    def run(self):
        self.sample_count = 0
        self.channel_samples = [TSLogger(dtype="float16") for c in self.analog_channels]
        yield from self.connect()


    @coroutine
    def try_to_connect(self):
        try:
            t = time.time()
            self.socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            self.socket.connect((self.addr, 1))
            self.socket.setblocking(False)
            print("%.2f" % (time.time()-t))
        except bluetooth.BluetoothError as e:
            print(e)
            return False
        return True


    @coroutine
    def connect(self):
        """ Try to connect to the device. This coroutine runs forever. """

        while 1:
            print("Trying to connect")
            # Loop until a connection is successful
            success = yield from self.try_to_connect()
            if success:
                print("Connection made!")
                if not self.connected.is_set():
                    self.connected.set()
                self.send_start()
                yield from self.read_loop()
            else:
                yield from sleep(3)


    def send_start(self):
        analog_channels = self.analog_channels
        command_start = 1
        for i in analog_channels:
            command_start = command_start | 1 << (2+i)
        command_rate = 3
        rate_command = bytes([(command_rate<<6) | 0x03])
        for i in range(2):
            self.socket.send(rate_command)
            self.socket.send(bytes([command_start]))


    def parser(self):
        # Not an asyncio coroutine!
        n = len(self.analog_channels)
        psize = packet_size(n)
        packet = np.zeros(psize, np.int8)
        sample = np.zeros(n)
        while 1:
            for i in range(psize):
                b = yield
                packet[i] = b
            packet_number = ((packet[-1] & 0xF0)>>4)

            crc = packet[-1] & 0x0F
            packet[-1] = packet[-1] & 0xF0
            x = 0
            for i in range(psize):
                for bit in range(7, -1, -1):
                    x = x << 1
                    if (x & 0x10):
                        x = x ^ 0x03
                    x = x ^ ((packet[i]>>bit) & 0x01)

            if crc != (x & 0x0f):
                print("Parser error!")
                raise BitalinoParserError()
            else:
                if n > 0:
                    sample[0] = ((packet[-2] & 0x0F) << 6) | (packet[-3] >> 2)
                if n > 1:
                    sample[1] = ((packet[-3] & 0x03) << 8) | packet[-4]
                if n > 2:
                    sample[2] = (packet[-5] << 2) | (packet[-6] >> 6)
                if n > 3:
                    sample[3] = ((packet[-6] & 0x3F) << 4) | (packet[-7] >> 4)
                if n > 4:
                    sample[4] = ((packet[-7] & 0x0F) << 2) | (packet[-8] >> 6)
                if n > 5:
                    sample[5] = packet[-8] & 0x3F

                self.sample_count += 1
                self.fragment_samples += 1
            for i in range(n):
                self.channel_samples[i].log(self.time_offset + self.fragment_samples * 1/self.rate, sample[i])

    @coroutine
    def read_loop(self):
        """ Reads repeatedly from bluetooth socket, and returns if errors are
            deemed unrecoverable. """
        parser = self.parser()
        next(parser)
        error_count = 0
        self.time_offset = None
        while 1:
            yield from sleep(0.01)
            try:
                buffer = self.socket.recv(10000)
                # If this is the first time data being read, guess
                # the starting time of the current read
                print(len(buffer))
                if len(buffer)>0:
                    t = time.time() - math.ceil(len(buffer) / self.rate \
                                / packet_size(len(self.analog_channels)))
                    self.time_offset = t
                    self.fragment_samples = 0

                    for b in buffer:
                        parser.send(b)
                # reset error count
                error_count = 0
            except bluetooth.BluetoothError as e:
                print("error on reading:", e)
                if str(e) == "(11, 'Resource temporarily unavailable')":
                    error_count += 1
                    if error_count > 2:
                        self.socket.close()
                        return
                    yield from sleep(1 + error_count*1/2)
                else:
                    self.socket.close()
                    yield from sleep(1)
                    return
            except BitalinoParserError as e:
                # Kill connection. We can't reconstruct the
                # timeline reliably otherwise.
                self.socket.send(bytes([0]))
                self.socket.send(bytes([0]))
                while len(self.socket.recv(10000)>0):
                    pass
                self.socket.close()
                return

class BitalinoStreamCommand(StreamerCommand):
    @coroutine
    def run(self, address=None, interval=1.0, **kwargs):
        if address not in bitalino_manager.devices:
            self.websocket.send(msg="bitalino_error",
                                error_name="address not connected",
                                description="No device with this address connected.")
            return
        device =  bitalino_manager.devices[address]

        last_index = device.sample_count
        print ("Bitalino Streaming")
        while True:
            yield from device.connected.wait()
            yield from sleep(interval)
            msg = dict(mtp="bitalino_stream",
                       address=address)
            for i, channel in enumerate(device.analog_channels):
                ts = device.channel_samples[i]
                values = ts.values[last_index:]
                times = ts.times[last_index:]
                msg["analog_%i" % channel ] = [times, values]
            s = message(**msg)
            yield from self.websocket.send(s)
            last_index = device.sample_count

