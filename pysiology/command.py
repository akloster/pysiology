from utils import fork


class ServerCommand(object):
    def __init__(self, websocket,**kwargs):
        self.websocket = websocket
        self.cancelled = False

    def __call__(self, **kwargs):
        self.task = fork(self.run(**kwargs))
    def stop(self, **kwargs):
        self.cancelled = True
        self.task.cancel()
    def cancel(self, **kwargs):
        self.cancelled = True
        self.task.cancel()

