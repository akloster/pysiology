import asyncio
import json
from asyncio import coroutine, sleep, async

class Streamer(object):
    """ Base class for streaming output. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stop = asyncio.Event()

    def make_message(self, **kwargs):
        d = dict(mtp="stream")
        d.update(kwargs)
        return json.dumps(d, cls=ArrayAwareJSONEncoder)

    @coroutine
    def run(self, message_queue):
        pass

