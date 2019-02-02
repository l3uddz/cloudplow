import logging
import random

from utils import process
from utils.rclone import RcloneSyncer

try:
    from shlex import quote as cmd_quote
except ImportError:
    from pipes import quote as cmd_quote

log = logging.getLogger("local")


class Local:
    NAME = 'Local'

    def __init__(self, tool_path, from_config, to_config, **kwargs):
        self.tool_path = tool_path
        self.sync_from_config = from_config
        self.sync_to_config = to_config
        self.kwargs = kwargs
        self.instance_id = None
        self.rclone_config_path = None

        log.info("Initialized Local syncer agent for %s -> %s using tool: %r", self.sync_from_config['sync_remote'],
                 self.sync_to_config['sync_remote'], self.tool_path)
        return

    def startup(self, **kwargs):
        if 'name' not in kwargs:
            log.error("You must provide an name for this instance")
            return False, None

        # fake instance_id
        self.instance_id = random.randint(1, 10000)

        return True, self.instance_id

    def setup(self, **kwargs):
        if not self.instance_id:
            log.error("Setup was called, but no instance_id was found, aborting...")
            return False
        if 'rclone_config' not in kwargs:
            log.error("Setup was called, but no rclone_config was found, aborting...")
            self.destroy()
            return False

        # store the rclone_config path provided in kwargs
        self.rclone_config_path = kwargs['rclone_config']

        return True

    def destroy(self, **kwargs):
        if not self.instance_id:
            log.error("Destroy was called, but no instance_id was found, aborting...")
            return False

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
        cmd = "%s %s --config=%s" % (
            cmd_quote(self.tool_path), cmd_quote(command[7:]), cmd_quote(self.rclone_config_path))
        return cmd
