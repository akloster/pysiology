from collections import defaultdict


class BaseParser(object):
    EEG_CHANNELS = ["LAUX", "TP9", "AF7", "AF8", "TP10", "RAUX"]
    def __init__(self):
        self.runner = self.run()
        self.runner.send(None)
    

    def feed_buffer(self, buffer):
        for b in buffer:
            self.send(b)
    def send(self, b):
        self.runner.send(b)
    def wait_for_sync(self):
        sync = b'\xff\xff\xaa\x55'
        i = 0
        while 1:
            b = yield
            if b == sync[i]:
                i+=1
                if i==len(sync):
                    return True
            else:
                i = 0
    def read_bytes(self, n):
        r = []
        for i in range(n):
            b = yield
            r.append(b)
        return r
    

    def read_raw_eeg(self):
        packet = yield from self.read_bytes(12)
        for i,channel in enumerate(self.EEG_CHANNELS):
            value = packet[i*2]*256 +packet[i*2+1]
            self.receive_value(channel, value)

        
    def read_accelerometer(self):
        packet = yield from self.read_bytes(4)

        
    def read_battery(self):
        packet = yield from self.read_bytes(8)
        battery_percent = packet[0]*256+packet[1]
        self.receive_value("battery_percent", battery_percent)
        
    def read_packet(self):
        b = yield
        if b == 0xe0:
            yield from self.read_raw_eeg()
            return True
        elif b == 0xa0:
            yield from self.read_accelerometer()
            return True
        elif b == 0xb0:
            yield from self.read_battery()
            return True
        elif b == 0xff:
            yield from self.read_bytes(3)
            #print("SYNC")
            return True
        else:
            # This should only happen in case of error flags / missing samples and only rarely
            print("#### %02x" % b)
            return False

    def run(self):
        while 1:
            yield from self.wait_for_sync()
            buffer = []
            good = True
            while good:
                good = yield from self.read_packet()
            for i in range(30):
                b = yield
                buffer.append(b)
            print(" ".join([ "%02x" % c for c in buffer]))


class Parser(BaseParser):
    def __init__(self):
        super().__init__()

    def receive_value(self, channel, value):
        print(channel, value)


class SimpleLoggingParser(Parser):
    """ Logs received values into a defaultdict. """
    def __init__(self):
        super().__init__()
        self.channels = defaultdict(list)

    def receive_value(self, channel, value):
        self.channels[channel].append(value)
