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
        self.region = kwargs.get('region', 'par1')
        # parse type from kwargs (default X64-2GB)
        self.type = kwargs.get('type', 'X64-2GB')
        # parse image from kwargs (default Ubuntu 16.04)
        self.image = kwargs.get('image', 'ubuntu-xenial')
        # parse instance_destroy from kwargs (default True)
        self.instance_destroy = kwargs.get('instance_destroy', True)
        self.syncer_name = kwargs.get('syncer_name', 'Unknown Syncer')

        log.info(f"Initialized Scaleway syncer agent for {self.syncer_name} - {self.sync_from_config['sync_remote']} -> {self.sync_to_config['sync_remote']} using tool: {self.tool_path}")
        return

    def startup(self, **kwargs):
        if 'name' not in kwargs:
            log.error("You must provide an name for this instance")
            return False, None

        # check if instance exists
        cmd = f"{cmd_quote(self.tool_path)} ps -a"
        resp = process.popen(cmd)
        if not resp or 'zone' not in resp.lower():
            log.error(f"Unexpected response while checking if instance {kwargs['name']} exists: {resp}")
            return False, self.instance_id

        if self.instance_destroy or kwargs['name'].lower() not in resp.lower():
            # create instance
            cmd = f"{cmd_quote(self.tool_path)} --region={cmd_quote(self.region)} run -d --name={cmd_quote(kwargs['name'])} --ipv6 --commercial-type={cmd_quote(self.type)} {cmd_quote(self.image)}"

            resp = self.start_instance(cmd, "Creating new instance...")
            if not resp or 'failed' in resp.lower():
                log.error(f"Unexpected response while creating instance: {resp}")
                return False, self.instance_id
            else:
                self.instance_id = resp
            log.info(f"Created new instance: {self.instance_id}")
        else:
            # start existing instance
            cmd = f"{cmd_quote(self.tool_path)} --region={cmd_quote(self.region)} start {cmd_quote(kwargs['name'])}"

            resp = self.start_instance(cmd, "Starting instance...")
            if not resp or 'failed' in resp.lower():
                log.error(f"Unexpected response while creating instance: {resp}")
                return False, kwargs['name']
            else:
                self.instance_id = kwargs['name']
            log.info(f"Started existing instance: {self.instance_id}")

        # wait for instance to finish booting
        log.info("Waiting for instance to finish booting...")
        time.sleep(60)
        cmd = f"{cmd_quote(self.tool_path)} --region={cmd_quote(self.region)} exec -w {cmd_quote(self.instance_id)} {cmd_quote('uname -a')}"

        log.debug(f"Using: {cmd}")

        resp = process.popen(cmd)
        if not resp or 'gnu/linux' not in resp.lower():
            log.error(f"Unexpected response while waiting for instance to boot: {resp}")
            self.destroy()
            return False, self.instance_id

        log.info(f"Instance has finished booting, uname: {resp}")
        return True, self.instance_id

    def start_instance(self, cmd, arg1):
        log.debug(f"Using: {cmd}")

        log.debug(arg1)
        return process.popen(cmd)

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
        cmd = f"{cmd_quote(self.tool_path)} --region={cmd_quote(self.region)} exec {cmd_quote(self.instance_id)} {cmd_quote(cmd_exec)}"

        log.debug(f"Using: {cmd}")

        log.debug(f"Installing rclone to instance: {self.instance_id}")
        resp = process.popen(cmd)
        if not resp or '/usr/bin/unzip' not in resp.lower():
            return self.error_handling(f"Unexpected response while installing unzip: {resp}")

        log.info("Installed unzip")

        # install rclone to instance
        cmd_exec = "cd ~ && curl -sO https://downloads.rclone.org/rclone-current-linux-amd64.zip && " \
                   "unzip -oq rclone-current-linux-amd64.zip && cd rclone-*-linux-amd64 && " \
                   "cp -rf rclone /usr/bin/ && cd ~ && rm -rf rclone-* && chown root:root /usr/bin/rclone && " \
                   "chmod 755 /usr/bin/rclone && mkdir -p /root/.config/rclone && which rclone"
        cmd = f"{cmd_quote(self.tool_path)} --region={cmd_quote(self.region)} exec {cmd_quote(self.instance_id)} {cmd_quote(cmd_exec)}"

        log.debug(f"Using: {cmd}")

        log.debug(f"Installing rclone to instance: {self.instance_id}")
        resp = process.popen(cmd)
        if not resp or '/usr/bin/rclone' not in resp.lower():
            return self.error_handling(f"Unexpected response while installing rclone: {resp}")

        log.info("Installed rclone")

        # copy rclone.conf to instance
        cmd = f"{cmd_quote(self.tool_path)} --region={cmd_quote(self.region)} cp {cmd_quote(kwargs['rclone_config'])} {cmd_quote(self.instance_id)}:/root/.config/rclone/"

        log.debug(f"Using: {cmd}")

        log.debug(f"Copying rclone config {kwargs['rclone_config']} to instance: {self.instance_id}")
        resp = process.popen(cmd)
        if resp is None or len(resp) >= 2:
            return self.error_handling(f"Unexpected response while copying rclone config: {resp}")

        log.info("Copied across rclone.conf")

        log.info(f"Successfully setup instance: {self.instance_id}")
        return True

    def error_handling(self, arg0, resp):
        log.error(arg0, resp)
        self.destroy()
        return False

    def destroy(self):
        if not self.instance_id:
            log.error("Destroy was called, but no instance_id was found, aborting...")
            return False

        if self.instance_destroy:
            # destroy the instance
            cmd = f"{cmd_quote(self.tool_path)} --region={cmd_quote(self.region)} rm -f {cmd_quote(self.instance_id)}"

            log.debug(f"Using: {cmd}")

            log.debug(f"Destroying instance: {self.instance_id}")
            resp = process.popen(cmd)
            if not resp or self.instance_id.lower() not in resp.lower():
                log.error(f"Unexpected response while destroying instance {self.instance_id}: {resp}")
                return False

            log.info(f"Destroyed instance: {self.instance_id}")
        else:
            # stop the instance
            cmd = f"{cmd_quote(self.tool_path)} --region={cmd_quote(self.region)} stop {cmd_quote(self.instance_id)}"

            log.debug(f"Using: {cmd}")

            log.debug(f"Stopping instance: {self.instance_id}")
            resp = process.popen(cmd)
            if not resp or self.instance_id.lower() not in resp.lower():
                log.error(f"Unexpected response while stopping instance {self.instance_id}: {resp}")
                return False

            log.info(f"Stopped instance: {self.instance_id}")

        return True

    def sync(self, **kwargs):
        if not self.instance_id:
            log.error("Sync was called, but no instance_id was found, aborting...")
            return False, None, None
        kwargs.update(self.kwargs)

        # create RcloneSyncer object
        rclone = RcloneSyncer(self.sync_from_config, self.sync_to_config, **kwargs)

        # start sync
        log.info(f"Starting sync for instance: {self.instance_id}")
        resp, delayed_check, delayed_trigger = rclone.sync(self._wrap_command)
        log.info(f"Finished syncing for instance: {self.instance_id}")

        # copy rclone.conf back from instance (in-case refresh tokens were used) (Copy seems not to be working atm)
        # cmd = "%s --region=%s cp %s:/root/.config/rclone/rclone.conf %s" % (
        #     cmd_quote(self.tool_path), cmd_quote(self.region), cmd_quote(self.instance_id),
        #     cmd_quote(os.path.dirname(kwargs['rclone_config'])))

        # Use exec cat > rclone config until cp is resolved
        cmd = f"{cmd_quote(self.tool_path)} --region={cmd_quote(self.region)} exec {cmd_quote(self.instance_id)} cat /root/.config/rclone/rclone.conf > {cmd_quote(kwargs['rclone_config'])}"

        log.debug(f"Using: {cmd}")

        log.debug(f"Copying rclone config from instance {self.instance_id} to: {kwargs['rclone_config']}")
        config_resp = process.popen(cmd, shell=True)
        if config_resp is None or len(config_resp) >= 2:
            log.error(f"Unexpected response while copying rclone config from instance: {config_resp}")
        else:
            log.info("Copied rclone.conf from instance")

        return resp, delayed_check, delayed_trigger

    # internals

    def _wrap_command(self, command):
        return f"{cmd_quote(self.tool_path)} --region={cmd_quote(self.region)} exec {cmd_quote(self.instance_id)} {cmd_quote(command)}"
