import asyncio
from asyncio import coroutine
import bcolz
import numpy as np
import json
from pysiology.np_json import ArrayAwareJSONEncoder

def name_task(name, task):
    @coroutine
    def wrapped():
        result = yield from task
        return (name, result)
    wrapped.__name__ = name
    return wrapped()

@coroutine
def first_completed(**kwargs):
    named_tasks = []
    tasks = []
    for k,v in kwargs.items():
        tasks.append(v)
        named_tasks.append(name_task(k, v))
    done, pending = yield from asyncio.wait(named_tasks, timeout=10,
            return_when=asyncio.FIRST_COMPLETED)
    results = [f.result() for f in done]
    for f in pending:
        f.cancel()
    return results



def fork(generator):
    """ Helper function to make "forking" in asyncio more obvious and less verbose. """
    fut = asyncio.get_event_loop().create_task(generator)
    def temp(self):
        #print("Done.", self.result())
        self.result()
    fut.add_done_callback(temp)


class TSLogger(object):
    def __init__(self, dtype="int16"):
        self.values = bcolz.carray([], dtype="int16")
        self.times = bcolz.carray([], dtype="float64")

    def log(self, time, value):
        self.values.append(value)
        self.times.append(time)

    def __len__(self):
        return len(self.times)

def message(**kwargs):
    return json.dumps(kwargs, cls=ArrayAwareJSONEncoder)
