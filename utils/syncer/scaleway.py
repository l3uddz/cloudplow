import logging

try:
    from shlex import quote as cmd_quote
except ImportError:
    from pipes import quote as cmd_quote

log = logging.getLogger("scaleway")


class Scaleway:
    NAME = 'Scaleway'

    def __init__(self, from_config, to_config, **kwargs):
        self.sync_from_config = from_config
        self.sync_to_config = to_config
        self.kwargs = kwargs

        # pass region from kwargs (default France)
        if 'region' in kwargs:
            self.region = kwargs['region']
        else:
            self.region = 'par1'
        # pass type from kwargs (default X64-2GB)
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
        cmd = "scw --region=%s run -d --ipv6 --commercial-type=%s %s" % (
        cmd_quote(self.region), cmd_quote(self.type), cmd_quote(self.image))
        # output from cmd above is the new server id (store this)
        # check for 'failed' inside the output to detect failure, otherwise store returned id for further use
        log.debug("Using: %s", cmd)
        return False

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
