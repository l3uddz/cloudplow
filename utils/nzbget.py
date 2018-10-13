import logging

from .xmlrpc import ServerProxy

log = logging.getLogger(__name__)


class Nzbget:
    def __init__(self, url):
        self.url = "%s/xmlrpc" % url
        self.xmlrpc = ServerProxy(self.url)

    def pause_queue(self):
        paused = False
        try:
            with self.xmlrpc as proxy:
                paused = proxy.pausedownload()
        except Exception:
            log.exception("Exception pausing NzbGet queue: ")
        return paused

    def resume_queue(self):
        resumed = False
        try:
            with self.xmlrpc as proxy:
                resumed = proxy.resumedownload()
        except Exception:
            log.exception("Exception resuming NzbGet queue: ")
        return resumed
