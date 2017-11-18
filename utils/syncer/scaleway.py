import logging

log = logging.getLogger("scaleway")


class Scaleway:
    def __init__(self, from_config, to_config, **kwargs):
        self.sync_from_config = from_config
        self.sync_to_config = to_config
        self.kwargs = kwargs
        log.info("Initialized Scaleway syncer agent with kwargs: %r", kwargs)

    def startup(self, **kwargs):
        pass

    def setup(self, **kwargs):
        pass

    def destroy(self, **kwargs):
        pass

    def sync(self, **kwargs):
        pass
