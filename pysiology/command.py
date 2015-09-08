from utils import fork


class ServerCommand(object):
    def __init__(self, websocket,**kwargs):
        self.websocket = websocket

    def __call__(self, **kwargs):
        self.task = fork(self.run(**kwargs))
    def stop(self, **kwargs):
        self.task.cancel()
    def cancel(self, **kwargs):
        self.task.cancel()

