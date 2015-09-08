import aiohttp
import asyncio
from asyncio import coroutine
import sys, traceback

import json

def message(**kwargs):
    return json.dumps(kwargs)

@coroutine
def mindwave_test(ws):
    ws.send_str(message(command="mindwave_connect",
                        address="74:E5:43:BE:42:50"))
    yield from asyncio.sleep(2)
    ws.send_str(message(command="mindwave_stream",
                        address="74:E5:43:BE:42:50",
                        interval=1.0))
@coroutine
def bitalino_test(ws):
    ws.send_str(message(command="bitalino_connect",
                        address="98:D3:31:40:1B:B0",
    ))
    yield from asyncio.sleep(2)
    ws.send_str(message(command="bitalino_stream",
                        address="98:D3:31:40:1B:B0",
    ))

@coroutine
def test():
    print ("connecting...")
    ws = yield from aiohttp.ws_connect(
            'http://localhost:9010')
    print ("connected")
    #ws.send_str(message(command="discover_bluetooth"))
    yield from asyncio.sleep(0.5)
    #yield from mindwave_test(ws)
    yield from bitalino_test(ws)
    while True:
        msg = yield from ws.receive()
        if msg.tp == aiohttp.MsgType.text:
            print("message:", msg.data)
        elif msg.tp == aiohttp.MsgType.closed:
            print("closed")
            break
        elif msg.tp == aiohttp.MsgType.error:
            print("error")
            break

@coroutine
def main():
    while 1:
        try:
            yield from test()
        except aiohttp.errors.ClientOSError:
            pass
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
        yield from asyncio.sleep(2)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
