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
        self.region = kwargs['region'] if 'region' in kwargs else 'par1'
        # parse type from kwargs (default X64-2GB)
        self.type = kwargs['type'] if 'type' in kwargs else 'X64-2GB'
        # parse image from kwargs (default Ubuntu 16.04)
        self.image = kwargs['image'] if 'image' in kwargs else 'ubuntu-xenial'
        # parse instance_destroy from kwargs (default True)
        self.instance_destroy = kwargs['instance_destroy'] if 'instance_destroy' in kwargs else True
        self.syncer_name = kwargs['syncer_name'] if 'syncer_name' in kwargs else 'Unknown Syncer'

        log.info("Initialized Scaleway syncer agent for %r - %s -> %s using tool: %r", self.syncer_name,
                 self.sync_from_config['sync_remote'], self.sync_to_config['sync_remote'], self.tool_path)
        return

    def startup(self, **kwargs):
        if 'name' not in kwargs:
            log.error("You must provide an name for this instance")
            return False, None

        # check if instance exists
        cmd = "%s ps -a" % cmd_quote(self.tool_path)
        resp = process.popen(cmd)
        if not resp or 'zone' not in resp.lower():
            log.error("Unexpected response while checking if instance %s exists: %s", kwargs['name'], resp)
            return False, self.instance_id

        if self.instance_destroy or kwargs['name'].lower() not in resp.lower():
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
        else:
            # start existing instance
            cmd = "%s --region=%s start %s" % (
                cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(kwargs['name']))
            log.debug("Using: %s", cmd)

            log.debug("Starting instance...")
            resp = process.popen(cmd)
            if not resp or 'failed' in resp.lower():
                log.error("Unexpected response while creating instance: %s", resp)
                return False, kwargs['name']
            else:
                self.instance_id = kwargs['name']
            log.info("Started existing instance: %r", self.instance_id)

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
        if not self.instance_id:
            log.error("Setup was called, but no instance_id was found, aborting...")
            return False
        if 'rclone_config' not in kwargs:
            log.error("Setup was called, but no rclone_config was found, aborting...")
            self.destroy()
            return False

        # install unzip
        cmd_exec = "apt-get -qq update && apt-get -y -qq install unzip && which unzip"
        cmd = "%s --region=%s exec %s %s" % (
            cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(self.instance_id), cmd_quote(cmd_exec))
        log.debug("Using: %s", cmd)

        log.debug("Installing rclone to instance: %r", self.instance_id)
        resp = process.popen(cmd)
        if not resp or '/usr/bin/unzip' not in resp.lower():
            log.error("Unexpected response while installing unzip: %s", resp)
            self.destroy()
            return False
        log.info("Installed unzip")

        # install rclone to instance
        cmd_exec = "cd ~ && curl -sO https://downloads.rclone.org/rclone-current-linux-amd64.zip && " \
                   "unzip -oq rclone-current-linux-amd64.zip && cd rclone-*-linux-amd64 && " \
                   "cp -rf rclone /usr/bin/ && cd ~ && rm -rf rclone-* && chown root:root /usr/bin/rclone && " \
                   "chmod 755 /usr/bin/rclone && mkdir -p /root/.config/rclone && which rclone"
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
        if not self.instance_id:
            log.error("Destroy was called, but no instance_id was found, aborting...")
            return False

        if self.instance_destroy:
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
        else:
            # stop the instance
            cmd = "%s --region=%s stop %s" % (
                cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(self.instance_id))
            log.debug("Using: %s", cmd)

            log.debug("Stopping instance: %r", self.instance_id)
            resp = process.popen(cmd)
            if not resp or self.instance_id.lower() not in resp.lower():
                log.error("Unexpected response while stopping instance %r: %s", self.instance_id, resp)
                return False

            log.info("Stopped instance: %r", self.instance_id)

        return True

    def sync(self, **kwargs):
        if not self.instance_id:
            log.error("Sync was called, but no instance_id was found, aborting...")
            return False, None, None
        kwargs.update(self.kwargs)

        # create RcloneSyncer object
        rclone = RcloneSyncer(self.sync_from_config, self.sync_to_config, **kwargs)

        # start sync
        log.info("Starting sync for instance: %r", self.instance_id)
        resp, delayed_check, delayed_trigger = rclone.sync(self._wrap_command)
        log.info("Finished syncing for instance: %r", self.instance_id)

        # copy rclone.conf back from instance (in-case refresh tokens were used) (Copy seems not to be working atm)
        # cmd = "%s --region=%s cp %s:/root/.config/rclone/rclone.conf %s" % (
        #     cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(self.instance_id),
        #     cmd_quote(os.path.dirname(kwargs['rclone_config'])))

        # Use exec cat > rclone config until cp is resolved
        cmd = "%s --region=%s exec %s cat /root/.config/rclone/rclone.conf > %s" % (
            cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(self.instance_id),
            cmd_quote(kwargs['rclone_config']))
        log.debug("Using: %s", cmd)

        log.debug("Copying rclone config from instance %r to: %r", self.instance_id, kwargs['rclone_config'])
        config_resp = process.popen(cmd, shell=True)
        if config_resp is None or len(config_resp) >= 2:
            log.error("Unexpected response while copying rclone config from instance: %s", config_resp)
        else:
            log.info("Copied rclone.conf from instance")

        return resp, delayed_check, delayed_trigger

    # internals

    def _wrap_command(self, command):
        cmd = "%s --region=%s exec %s %s" % (
            cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(self.instance_id), cmd_quote(command))
        return cmd
