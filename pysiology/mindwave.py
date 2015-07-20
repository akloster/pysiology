"""
	Mindwave Driver
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
from utils import TSLogger
from streamer import Streamer
from np_json import ArrayAwareJSONEncoder
import json


class MindwaveManager(SampleSource):
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
                yield from sleep(0.25)
                try:
                    buffer = self.socket.recv(10000)
                    self.raw_counter = 0
                    for b in buffer:
                        parser.send(b)
                    self.time_offset = time.time()
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

value_names = ["attention", "meditation", "poor_signal", "blink_strength", "raw"]

class MindwaveStreamer(Streamer):
    def __init__(self, mindwave_manager, interval):
        self.interval = interval
        self.mindwave_manager= mindwave_manager
        m = mindwave_manager

    @coroutine
    def run(self, message_queue):
        self.last_index = 0

        last_indices = self.mindwave_manager.get_indices()
        while True:
            msg = dict(mtp="mindwave-stream")
            for name in value_names:
                ts = getattr(self.mindwave_manager, name)
                last_index = last_indices[name]
                values = ts.values[last_index:]
                times = ts.times[last_index:]
                #print (name, " ", len(values), " ", len(times))
                msg[name] = [times, values]

            msg = json.dumps(msg, cls=ArrayAwareJSONEncoder)
            #print(msg)
            yield from message_queue.put(msg)
            last_indices = self.mindwave_manager.get_indices()
            yield from sleep(self.interval)

