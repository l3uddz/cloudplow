import copy
import threading


class Thread:
    def __init__(self):
        self.threads = []

    def start(self, target, name=None, args=None, track=False):
        thread = threading.Thread(target=target, name=name, args=args if args else [])
        thread.daemon = True
        thread.start()
        if track:
            self.threads.append(thread)
        return thread

    def join(self):
        for thread in copy.copy(self.threads):
            thread.join()
            self.threads.remove(thread)
        return
