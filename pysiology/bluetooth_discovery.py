import asyncio
import bluetooth
from asyncio import coroutine, sleep, async, wait, gather
from utils import fork, message, first_completed
from command import ServerCommand


class AsyncDiscoverer(bluetooth.DeviceDiscoverer):
    """ This is pybluez' attempt at customizing the discovery process.
        This class contains callbacks for various parts of the process.
        However, the documentation doesn't exactly tell you that you need
        to call BluetoothDiscoverer.process_event() explicitly!
    """
    def device_discovered(self, address, device_class, name, sth):
        # put events into an asyncio Queue
        self.queue.put_nowait((address,  device_class, name, sth))

    def pre_inquiry(self):
        self.done = False

    def inquiry_complete(self):
        self.done = True
        

class DiscoverBluetoothCommand(ServerCommand):
    @coroutine
    def run(self, **kwargs):
        self.device_events = asyncio.Queue()
        known_addresses = []
        print("Looking for devices")
        while 1:
            try:
                bd = AsyncDiscoverer()
                bd.queue = self.device_events
                bd.find_devices(lookup_names=False, duration=5)
            except bluetooth.BluetoothError:
                # An exception at this stage is a very bad sign. Probably no BT adapter
                # is available.
                print("Error encountered while scanning for bluetooth devices.")
            for i in range(3):
                try:
                    bd.process_event()
                except bluetooth._bluetooth.error as e:
                    print(e)
                    pass
                except TypeError as e:
                    print(e)
                if bd.done:
                    break
                
                try:
                    event = self.device_events.get_nowait()
                except asyncio.QueueEmpty:
                    yield from sleep(0.1)
                    continue

                address = event[0]
                if address not in known_addresses:
                    known_addresses.append(address)
                    name =  bluetooth.lookup_name(address, timeout=10)
                    print("Bluetooth device:", address, name)
                    yield from self.websocket.send(message(msg="bluetooth_device_discovered",
                                                address=address,
                                                name=name))
        print("Bluetooth Discovery finished.")
        yield from self.websocket.send(message(msg="bluetooth_discovery_finished"))


