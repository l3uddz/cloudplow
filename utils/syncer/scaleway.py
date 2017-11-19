import logging

log = logging.getLogger("scaleway")


class Scaleway:
    def __init__(self, from_config, to_config, **kwargs):
        self.kwargs = kwargs
        self.sync_from_config = from_config
        self.sync_to_config = to_config

        # pass region from kwargs (default France)
        if 'region' in kwargs:
            self.region = kwargs['region']
        else:
            self.region = 'par1'
        # pass commercial-type from kwargs (default X64-2GB)
        if 'type' in kwargs:
            self.type = kwargs['type']
        else:
            self.type = 'X64-2GB'
        # pass image from kwargs (default Ubuntu 16.04)
        if 'image' in kwargs:
            self.image = kwargs['image']
        else:
            self.image = 'ubuntu-xenial'

        log.info("Initialized Scaleway syncer agent with kwargs: %r", kwargs)

    def startup(self):
        cmd = "scw --region=%s run -d --ipv6 --commercial-type=%s %s" % (self.region, self.type, self.image)
        # output from cmd above is the new server id (store this)
        # check for 'failed' inside the output to determine success / failure
        pass

    def setup(self):
        # install rclone to instance
        # copy rclone.conf to instance
        pass

    def destroy(self):
        # destroy the instance
        pass

    def sync(self):
        # run rclone sync
        pass
