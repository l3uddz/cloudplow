import logging

from .scaleway import Scaleway

log = logging.getLogger("syncer")

SERVICES = {
    'scaleway': Scaleway
}


class Syncer:
    def __init__(self):
        self.services = []

    def load(self, **kwargs):
        if 'service' not in kwargs:
            log.error("You must specify a service to load with the service parameter")
            return False
        elif kwargs['service'] not in SERVICES:
            log.error("You specified an invalid service to load: %s", kwargs['service'])
            return False

        try:
            chosen_service = SERVICES[kwargs['service']]
            del kwargs['service']

            # load service
            service = chosen_service(**kwargs)
            self.services.append(service)

        except Exception:
            log.exception("Exception while loading service, kwargs=%r: ", kwargs)
