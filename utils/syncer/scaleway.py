import logging

from utils import process

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

        # vars used by script
        self.instance_id = None

        log.info("Initialized Scaleway syncer agent with kwargs: %r", kwargs)

    def startup(self):
        # create instance
        log.debug("Creating new instance...")
        cmd = "scw --region=%s run -d --ipv6 --commercial-type=%s %s" % (
            cmd_quote(self.region), cmd_quote(self.type), cmd_quote(self.image))
        log.debug("Using: %s", cmd)

        resp = process.popen(cmd)
        if 'failed' in resp.lower():
            log.error("Unexpected response while creating instance: %s", resp)
            return False
        else:
            self.instance_id = resp
        log.info("Created new instance: %r", self.instance_id)

        # wait for instance to finish booting
        log.info("Waiting for instance to finish booting...")
        cmd = "scw --region=%s exec -w %s %s" % (
            cmd_quote(self.region), cmd_quote(self.instance_id), cmd_quote('uname -a'))
        log.debug("Using: %s", cmd)

        resp = process.popen(cmd)
        if 'gnu/linux' not in resp.lower():
            log.error("Unexpected response while waiting for instance to boot: %s", resp)
            self.destroy()
            return False
        log.info("Instance has finished booting, uname: %r", resp)
        return True

    def setup(self):
        # install rclone to instance
        # copy rclone.conf to instance
        pass

    def destroy(self):
        if not self.instance_id or '-' not in self.instance_id:
            log.debug("Destroy was called, but no instance_id was found, aborting...")
            return False

        # destroy the instance
        cmd = "scw --region=%s rm -f %s" % (cmd_quote(self.region), cmd_quote(self.instance_id))
        log.debug("Using: %s", cmd)

        resp = process.popen(cmd)
        if self.instance_id.lower() not in resp.lower():
            log.error("Unexpected response while destroying instance %r: %s", self.instance_id, resp)
            return False
        return True

    def sync(self):
        # run rclone sync
        pass