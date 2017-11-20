import logging
import uuid

from .scaleway import Scaleway

log = logging.getLogger("syncer")

SERVICES = {
    'scaleway': Scaleway
}


class Syncer:
    def __init__(self, config):
        self.config = config
        self.services = []

    def load(self, **kwargs):
        # validate required keywords were supplied
        if 'service' not in kwargs:
            log.error("You must specify a service to load with the service parameter")
            return False
        elif kwargs['service'] not in SERVICES:
            log.error("You specified an invalid service to load: %s", kwargs['service'])
            return False

        if 'sync_from' not in kwargs or 'sync_to' not in kwargs:
            log.error("You must specify a sync_form and sync_to in your configuration")
            return False

        try:
            # retrieve remotes config for sync_from and sync_to
            sync_from_config = self.config['remotes'][kwargs['sync_from']]
            sync_to_config = self.config['remotes'][kwargs['sync_to']]

            # clean kwargs before initializing the service
            chosen_service = SERVICES[kwargs['service']]
            del kwargs['service']
            del kwargs['sync_from']
            del kwargs['sync_to']

            # load service
            service = chosen_service(sync_from_config, sync_to_config, **kwargs)
            self.services.append(service)

        except Exception:
            log.exception("Exception while loading service, kwargs=%r: ", kwargs)

    """
        Commands below take 1 or 2 keyword parameter (service and name).
    """

    def startup(self, **kwargs):
        if 'service' not in kwargs:
            log.error("You must specify a service to startup")
            return False
        if 'name' not in kwargs:
            name = str(uuid.uuid4())
        else:
            name = kwargs['name']

        try:
            chosen_service = kwargs['service']
            for syncer in self.services:
                if chosen_service and syncer.NAME.lower() != chosen_service:
                    continue
                return syncer.startup(name=name)
        except Exception:
            log.exception("Exception starting instance kwargs=%r: ", kwargs)

    """
        Commands below take 1 or 2 keyword parameter (service and instance_id).
    """

    def setup(self, **kwargs):
        if 'service' not in kwargs:
            log.error("You must specify a service to setup")
            return False

        try:
            chosen_service = kwargs['service']
            for syncer in self.services:
                if chosen_service and syncer.NAME.lower() != chosen_service:
                    continue
                # ignore syncer if instance_id does not match otherwise setup all syncers from service
                if 'instance_id' in kwargs and syncer.instance_id != kwargs['instance_id']:
                    continue
                return syncer.setup()
        except Exception:
            log.exception("Exception setting up instance kwargs=%r: ", kwargs)

    def destroy(self, **kwargs):
        if 'service' not in kwargs:
            log.error("You must specify a service to destroy")
            return False

        try:
            chosen_service = kwargs['service']
            for syncer in self.services:
                if chosen_service and syncer.NAME.lower() != chosen_service:
                    continue
                # ignore syncer if instance_id does not match otherwise destroy all syncers from service
                if 'instance_id' in kwargs and syncer.instance_id != kwargs['instance_id']:
                    continue
                return syncer.destroy()
        except Exception:
            log.exception("Exception destroying instance kwargs=%r: ", kwargs)

    def sync(self, **kwargs):
        pass
