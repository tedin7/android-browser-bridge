"""Order compound MCP actions while allowing independent pages to run together."""
import threading
from contextlib import contextmanager


class CommandOrder:
    def __init__(self):
        self.changed = threading.Condition()
        self.waiting = []
        self.active = set()
        self.global_devices = set()

    @contextmanager
    def enter(self, device, operation, args):
        if not isinstance(device,str) or not isinstance(operation,str) or not isinstance(args,dict):
            raise ValueError('Invalid device, operation or arguments')
        tab = args.get('tabId')
        if tab is not None and (isinstance(tab,bool) or not isinstance(tab,int)):
            raise ValueError('tabId must be an integer')
        global_action = tab is None or operation in {'open', 'activate', 'foreground', 'close', 'batch'}
        lane = (device, tab)
        ticket = {'token': object(), 'device': device, 'lane': lane, 'global': global_action}
        with self.changed:
            self.waiting.append(ticket)
            while True:
                earlier = self.waiting[:self.waiting.index(ticket)]
                conflict = device in self.global_devices or any(item['device'] == device and
                    (item['global'] or global_action or item['lane'] == lane) for item in earlier)
                conflict = conflict or (any(item[0] == device for item in self.active) if global_action else lane in self.active)
                if not conflict:
                    self.waiting.remove(ticket)
                    if global_action: self.global_devices.add(device)
                    else: self.active.add(lane)
                    break
                self.changed.wait()
        try:
            yield
        finally:
            with self.changed:
                if global_action: self.global_devices.remove(device)
                else: self.active.remove(lane)
                self.changed.notify_all()
