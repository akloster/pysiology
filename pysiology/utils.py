import asyncio
import bcolz
import numpy as np


def fork(generator):
    """ Helper function to make "forking" in asyncio more obvious and less verbose. """
    return asyncio.get_event_loop().create_task(generator)



class TSLogger(object):
    def __init__(self, dtype="int16"):
        self.values = bcolz.carray([], dtype="int16")
        self.times = bcolz.carray([], dtype="float64")

    def log(self, time, value):
        self.values.append(value)
        self.times.append(time)

    def __len__(self):
        return len(self.times)
