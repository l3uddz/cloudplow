import socket
import xmlrpc.client

""" referemce: https://stackoverflow.com/a/14397619 """


class ServerProxy:
    def __init__(self, url, timeout=10):
        self.__url = url
        self.__timeout = timeout
        self.__prevDefaultTimeout = None

    def __enter__(self):
        try:
            if self.__timeout:
                self.__prevDefaultTimeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(self.__timeout)
            proxy = xmlrpc.client.ServerProxy(self.__url, allow_none=True)
        except Exception as ex:
            raise Exception("Unable create XMLRPC-proxy for url '%s': %s" % (self.__url, ex))
        return proxy

    def __exit__(self, type, value, traceback):
        if self.__prevDefaultTimeout is None:
            socket.setdefaulttimeout(self.__prevDefaultTimeout)
