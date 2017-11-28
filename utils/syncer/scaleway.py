import logging
import time

from utils import process
from utils.rclone import RcloneSyncer

try:
    from shlex import quote as cmd_quote
except ImportError:
    from pipes import quote as cmd_quote

log = logging.getLogger("scaleway")


class Scaleway:
    NAME = 'Scaleway'

    def __init__(self, tool_path, from_config, to_config, **kwargs):
        self.tool_path = tool_path
        self.sync_from_config = from_config
        self.sync_to_config = to_config
        self.kwargs = kwargs
        self.instance_id = None

        # parse region from kwargs (default France)
        if 'region' in kwargs:
            self.region = kwargs['region']
        else:
            self.region = 'par1'
        # parse type from kwargs (default X64-2GB)
        if 'type' in kwargs:
            self.type = kwargs['type']
        else:
            self.type = 'X64-2GB'
        # parse image from kwargs (default Ubuntu 16.04)
        if 'image' in kwargs:
            self.image = kwargs['image']
        else:
            self.image = 'ubuntu-xenial'

        log.info("Initialized Scaleway syncer agent for %s -> %s using tool: %r", self.sync_from_config['sync_remote'],
                 self.sync_to_config['sync_remote'], self.tool_path)
        return

    def startup(self, **kwargs):
        if 'name' not in kwargs:
            log.error("You must provide an name for this instance")
            return False, None

        # create instance
        cmd = "%s --region=%s run -d --name=%s --ipv6 --commercial-type=%s %s" % (
            cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(kwargs['name']), cmd_quote(self.type),
            cmd_quote(self.image))
        log.debug("Using: %s", cmd)

        log.debug("Creating new instance...")
        resp = process.popen(cmd)
        if not resp or 'failed' in resp.lower():
            log.error("Unexpected response while creating instance: %s", resp)
            return False, self.instance_id
        else:
            self.instance_id = resp
        log.info("Created new instance: %r", self.instance_id)

        # wait for instance to finish booting
        log.info("Waiting for instance to finish booting...")
        time.sleep(60)
        cmd = "%s --region=%s exec -w %s %s" % (
            cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(self.instance_id), cmd_quote('uname -a'))
        log.debug("Using: %s", cmd)

        resp = process.popen(cmd)
        if not resp or 'gnu/linux' not in resp.lower():
            log.error("Unexpected response while waiting for instance to boot: %s", resp)
            self.destroy()
            return False, self.instance_id

        log.info("Instance has finished booting, uname: %r", resp)
        return True, self.instance_id

    def setup(self, **kwargs):
        if not self.instance_id or '-' not in self.instance_id:
            log.error("Setup was called, but no instance_id was found, aborting...")
            return False
        if 'rclone_config' not in kwargs:
            log.error("Setup was called, but no rclone_config was found, aborting...")
            self.destroy()
            return False

        # install unzip
        cmd_exec = "apt-get -qq update && apt-get -y -qq install unzip"
        cmd = "%s --region=%s exec %s %s" % (
            cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(self.instance_id), cmd_quote(cmd_exec))
        log.debug("Using: %s", cmd)

        log.debug("Installing rclone to instance: %r", self.instance_id)
        resp = process.popen(cmd)
        if not resp or 'setting up unzip' not in resp.lower():
            log.error("Unexpected response while installing unzip: %s", resp)
            self.destroy()
            return False
        log.info("Installed unzip")

        # install rclone to instance
        cmd_exec = "curl -sO https://downloads.rclone.org/rclone-current-linux-amd64.zip && " \
                   "unzip -q rclone-current-linux-amd64.zip && cd rclone-*-linux-amd64 && " \
                   "cp rclone /usr/bin/ && chown root:root /usr/bin/rclone && chmod 755 /usr/bin/rclone && " \
                   "mkdir -p /root/.config/rclone && which rclone"
        cmd = "%s --region=%s exec %s %s" % (
            cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(self.instance_id), cmd_quote(cmd_exec))
        log.debug("Using: %s", cmd)

        log.debug("Installing rclone to instance: %r", self.instance_id)
        resp = process.popen(cmd)
        if not resp or '/usr/bin/rclone' not in resp.lower():
            log.error("Unexpected response while installing rclone: %s", resp)
            self.destroy()
            return False
        log.info("Installed rclone")

        # copy rclone.conf to instance
        cmd = "%s --region=%s cp %s %s:/root/.config/rclone/" % (
            cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(kwargs['rclone_config']),
            cmd_quote(self.instance_id))
        log.debug("Using: %s", cmd)

        log.debug("Copying rclone config %r to instance: %r", kwargs['rclone_config'], self.instance_id)
        resp = process.popen(cmd)
        if resp is None or len(resp) >= 2:
            log.error("Unexpected response while copying rclone config: %s", resp)
            self.destroy()
            return False
        log.info("Copied across rclone.conf")

        log.info("Successfully setup instance: %r", self.instance_id)
        return True

    def destroy(self, **kwargs):
        if not self.instance_id or '-' not in self.instance_id:
            log.error("Destroy was called, but no instance_id was found, aborting...")
            return False

        # destroy the instance
        cmd = "%s --region=%s rm -f %s" % (
            cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(self.instance_id))
        log.debug("Using: %s", cmd)

        log.debug("Destroying instance: %r", self.instance_id)
        resp = process.popen(cmd)
        if not resp or self.instance_id.lower() not in resp.lower():
            log.error("Unexpected response while destroying instance %r: %s", self.instance_id, resp)
            return False

        log.info("Destroyed instance: %r", self.instance_id)
        return True

    def sync(self, **kwargs):
        if not self.instance_id or '-' not in self.instance_id:
            log.error("Sync was called, but no instance_id was found, aborting...")
            return False, None, None
        kwargs.update(self.kwargs)

        # create RcloneSyncer object
        rclone = RcloneSyncer(self.sync_from_config, self.sync_to_config, **kwargs)

        # start sync
        log.info("Starting sync for instance: %r", self.instance_id)
        resp, delayed_check, delayed_trigger = rclone.sync(self._wrap_command)
        log.info("Finished syncing for instance: %r", self.instance_id)

        return resp, delayed_check, delayed_trigger

    # internals

    def _wrap_command(self, command):
        cmd = "%s --region=%s exec %s %s" % (
            cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(self.instance_id), cmd_quote(command))
        return cmd
