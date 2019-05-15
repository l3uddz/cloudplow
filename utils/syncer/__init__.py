import logging
import uuid

from .local import Local
from .scaleway import Scaleway

log = logging.getLogger("syncer")

SERVICES = {
    'scaleway': Scaleway,
    'local': Local
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

        if 'tool_path' not in kwargs:
            log.error("You must specify a tool_path for each syncer in your service")
            return False

        if 'sync_from' not in kwargs or 'sync_to' not in kwargs:
            log.error("You must specify a sync_form and sync_to in your configuration")
            return False

        try:
            # retrieve remotes config for sync_from and sync_to
            sync_from_config = self.config['remotes'][kwargs['sync_from']]
            sync_to_config = self.config['remotes'][kwargs['sync_to']]

            # clean kwargs before initializing the service
            tool_path = kwargs['tool_path']
            chosen_service = SERVICES[kwargs['service']]
            del kwargs['service']
            del kwargs['sync_from']
            del kwargs['sync_to']
            del kwargs['tool_path']

            # load service
            service = chosen_service(tool_path, sync_from_config, sync_to_config, **kwargs)
            self.services.append(service)

        except Exception:
            log.exception("Exception while loading service, kwargs=%r: ", kwargs)

    """
        Methods below require minimum 1 or 2 keyword parameter (service and name).
    """

    def startup(self, **kwargs):
        if 'service' not in kwargs:
            log.error("You must specify a service to startup")
            return False
        if 'name' not in kwargs:
            kwargs['name'] = str(uuid.uuid4())

        try:
            # clean kwargs before passing this on
            chosen_service = kwargs['service']
            del kwargs['service']

            for syncer in self.services:
                if chosen_service and syncer.NAME.lower() != chosen_service:
                    continue
                if syncer.syncer_name != kwargs['name']:
                    continue

                return syncer.startup(**kwargs)
        except Exception:
            log.exception("Exception starting instance kwargs=%r: ", kwargs)

    """
        Methods below require minimum 1 or 2 keyword parameter (service and instance_id).
    """

    def setup(self, **kwargs):
        if 'service' not in kwargs:
            log.error("You must specify a service to setup")
            return False

        try:
            # clean kwargs before passing this on
            chosen_service = kwargs['service']
            del kwargs['service']

            for syncer in self.services:
                if chosen_service and syncer.NAME.lower() != chosen_service:
                    continue
                # ignore syncer if instance_id does not match otherwise setup all syncers from service
                if 'instance_id' in kwargs and syncer.instance_id != kwargs['instance_id']:
                    continue
                return syncer.setup(**kwargs)
        except Exception:
            log.exception("Exception setting up instance kwargs=%r: ", kwargs)

    def destroy(self, **kwargs):
        if 'service' not in kwargs:
            log.error("You must specify a service to destroy")
            return False

        try:
            # clean kwargs before passing this on
            chosen_service = kwargs['service']
            del kwargs['service']

            for syncer in self.services:
                if chosen_service and syncer.NAME.lower() != chosen_service:
                    continue
                # ignore syncer if instance_id does not match otherwise destroy all syncers from service
                if 'instance_id' in kwargs and syncer.instance_id != kwargs['instance_id']:
                    continue
                return syncer.destroy(**kwargs)
        except Exception:
            log.exception("Exception destroying instance kwargs=%r: ", kwargs)

    def sync(self, **kwargs):
        if 'service' not in kwargs:
            log.error("You must specify a service to sync")
            return False

        try:
            # clean kwargs before passing this on
            chosen_service = kwargs['service']
            del kwargs['service']

            for syncer in self.services:
                if chosen_service and syncer.NAME.lower() != chosen_service:
                    continue
                # ignore syncer if instance_id does not match otherwise destroy all syncers from service
                if 'instance_id' in kwargs and syncer.instance_id != kwargs['instance_id']:
                    continue
                return syncer.sync(**kwargs)
        except Exception:
            log.exception("Exception syncing instance kwargs=%r: ", kwargs)
