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
from sample_source import SampleSource
from streamer import Streamer


def packet_size(nChannels):
    if nChannels>4:
        return int(math.ceil((52.+6.*(nChannels-4))/8.))
    else:
        return int(math.ceil((12.+10.*(nChannels))/8.))


class BitalinoParserError(Exception):
    pass



class BitalinoPeriodicStreamer(Streamer):
    """ Simply streams one Bitalino channel. """
    def __init__(self, bitalino_manager, channel, interval, stretch,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bitalino_manager = bitalino_manager
        self.channel = channel
        try:
            interval = float(interval)
        except:
            interval = 1
        try:
            stretch = float(stretch)
        except:
            stretch = 5

        self.interval = interval
        self.stretch = stretch


    @coroutine
    def run(self, message_queue):
        self.last_segment = len(self.bitalino_manager.segments)-1
        self.last_sample = self.bitalino_manager.sample_count

        while True:
            if self.bitalino_manager.sample_count == 0:
                yield from sleep(self.interval)
            else:
                #values = self.bitalino_manager.get_all_since(self.channel, self.last_segment, self.last_sample)
                values = self.bitalino_manager.get_last_n_seconds(self.channel,5)
                self.last_segment = len(self.bitalino_manager.segments)-1
                self.last_sample = self.bitalino_manager.sample_count

                values = np.array(values, dtype=np.float16)
                time_offset = self.bitalino_manager.time_offset+len(values)\
                              / self.bitalino_manager.rate

                msg = self.make_message(channel=self.channel,
                                        values=values,
                                        time_offset=time_offset
                                        )

                yield from message_queue.put(msg)
                yield from sleep(self.interval)


class BitalinoManager(SampleSource):
    def __init__(self, addr):
        super().__init__()
        self.addr = addr
        self.record = True
        self.sample_count = 0
        self.analog_channels = (0, 2, 3)
        self.rate = 1000
        self.time_offset = None
        n = len(self.analog_channels)

        self.segments = []

    @coroutine
    def run(self):
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

        n = len(self.analog_channels)
        while 1:
            self.channel_samples = [bcolz.carray([], dtype=np.float16) for i in range(n)]
            self.sample_count = 0
            print("Trying to connect")
            # Loop until a connection is successful

            success = yield from self.try_to_connect()
            if success:
                print("Connection made!")
                self.send_start()
                self.segments.append(self.channel_samples)
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

            for i in range(n):
                self.channel_samples[i].append(sample[i])

    @coroutine
    def read_loop(self):
        """ Reads repeatedly from bluetooth socket, and returns if errors are
            deemed unrecoverable. """
        parser = self.parser()
        next(parser)
        error_count = 0
        self.time_offset = None
        while 1:
            yield from sleep(1)
            if self.record:
                t = time.time()
                yield from sleep(0.05)
                try:
                    buffer = self.socket.recv(10000)
                    # If this is the first time data is being read, guess
                    # the starting time of the current read
                    if self.time_offset is None:
                        t = time.time() - len(buffer) / self.rate
                        self.time_offset = t

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
            else:
                yield from sleep(0.5)

    def get_last_n_seconds(self, channel, n):
        m = int(min(n * self.rate, self.sample_count))
        if m==0:
            return bcolz.carray([], dtype=np.float16)
        else:
            return self.channel_samples[channel][-m:]

    def get_all_since(self, channel, last_segment, last_sample):
        channel_data = self.segments[last_segment][channel]
        if last_sample > len(channel_data):
            last_sample = 0
        return channel_data[last_sample:]

