import glob
import logging
import os
import time
from urllib.parse import urljoin
import re
import requests
import urllib3
import subprocess
import jsonpickle
from . import process, misc

try:
    from shlex import quote as cmd_quote
except ImportError:
    from pipes import quote as cmd_quote

log = logging.getLogger('rclone')

urllib3.disable_warnings()


class RcloneMover:
    def __init__(self, config, rclone_binary_path, rclone_config_path, plex, dry_run=False):
        self.config = config
        self.rclone_binary_path = rclone_binary_path
        self.rclone_config_path = rclone_config_path
        self.plex = plex
        self.dry_run = dry_run

    def move(self):
        try:
            log.debug(f"Moving '{self.config['move_from_remote']}' to '{self.config['move_to_remote']}'")

            # build cmd
            cmd = f"{cmd_quote(self.rclone_binary_path)} move {cmd_quote(self.config['move_from_remote'])} {cmd_quote(self.config['move_to_remote'])} --config={cmd_quote(self.rclone_config_path)}"

            extras = self.__extras2string()
            if len(extras) > 2:
                cmd += f' {extras}'
            excludes = self.__excludes2string()
            if len(excludes) > 2:
                cmd += f' {excludes}'
            if self.plex.get('enabled'):
                r = re.compile(r"https?://(www\.)?")
                rc_url = r.sub('', self.plex['rclone']['url']).strip().strip('/')
                cmd += f' --rc --rc-addr={cmd_quote(rc_url)}'
            if self.dry_run:
                cmd += ' --dry-run'

            # exec
            log.debug(f"Using: {cmd}")
            process.execute(cmd, logs=True)
            return True

        except Exception:
            log.exception(f"Exception occurred while moving '{self.config['move_from_remote']}' to '{self.config['move_to_remote']}':")

        return False

    # internals
    def __extras2string(self):
        if 'rclone_extras' not in self.config:
            return ''

        return ' '.join(f"{key}={cmd_quote(value) if isinstance(value, str) else value}" for (key, value) in self.config['rclone_extras'].items()).replace('=None', '').strip()

    def __excludes2string(self):
        if 'rclone_excludes' not in self.config:
            return ''

        return ' '.join(f"--exclude={cmd_quote(glob.escape(value) if value.startswith(os.path.sep) else value) if isinstance(value,str) else value}" for value in self.config['rclone_excludes']).replace('=None', '').strip()


class RcloneUploader:
    def __init__(self, name, config, rclone_binary_path, rclone_config_path, plex, dry_run=False,
                 service_account=None):
        self.name = name
        self.config = config
        self.rclone_binary_path = rclone_binary_path
        self.rclone_config_path = rclone_config_path
        self.plex = plex
        self.dry_run = dry_run
        self.service_account = service_account

    def delete_file(self, path):
        try:
            log.debug(f"Deleting file '{path}' from remote {self.name}")
            cmd = f"{cmd_quote(self.rclone_binary_path)} delete {cmd_quote(path)} --config={cmd_quote(self.rclone_config_path)} --user-agent={cmd_quote('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36')}"

            if self.dry_run:
                cmd += ' --dry-run'
            log.debug(f"Using: {cmd}")
            resp = process.execute(cmd, logs=False)
            return 'Failed to delete' not in resp
        except Exception:
            log.exception(f"Exception deleting file '{path}' from remote {self.name}: ")
        return False

    def delete_folder(self, path):
        try:
            log.debug(f"Deleting folder '{path}' from remote {self.name}")
            cmd = f"{cmd_quote(self.rclone_binary_path)} rmdir {cmd_quote(path)} --config={cmd_quote(self.rclone_config_path)} --user-agent={cmd_quote('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36')}"

            if self.dry_run:
                cmd += ' --dry-run'
            log.debug("Using: %s", cmd)
            resp = process.execute(cmd, logs=False)
            return 'Failed to rmdir' not in resp
        except Exception:
            log.exception(f"Exception deleting folder '{path}' from remote {self.name}: ")

        return False

    def upload(self, callback):
        try:
            log.debug(f"Uploading '{self.config['upload_folder']}' to '{self.config['upload_remote']}'")
            log.debug(f"Rclone command set to '{self.config['rclone_command'] if ('rclone_command' in self.config and self.config['rclone_command'].lower() != 'sync') else 'move'}'")
            # build cmd
            cmd = f"{cmd_quote(self.rclone_binary_path)} {cmd_quote(self.config['rclone_command'] if ('rclone_command' in self.config and self.config['rclone_command'].lower() != 'sync') else 'move')} {cmd_quote(self.config['upload_folder'])} {cmd_quote(self.config['upload_remote'])} --config={cmd_quote(self.rclone_config_path)}"
            subprocess_env = os.environ.copy()

            if self.service_account is not None:

                rclone_data = subprocess.check_output(f'rclone config dump --config={cmd_quote(self.rclone_config_path)}', shell=True)
                rclone_remotes = jsonpickle.decode(rclone_data)
                config_remote = self.config['upload_remote'].split(":")[0]

                def find_crypt_upstream(crypt_remote):
                    crypt_remote_upstream = rclone_remotes[crypt_remote]['remote'].split(":")[0]
                    try:
                        crypt_upstream_remote_type = rclone_remotes[crypt_remote_upstream]['type']
                        if crypt_upstream_remote_type == "drive":
                            return [crypt_remote_upstream]
                        elif crypt_upstream_remote_type == "union":
                            return find_union_upstreams(crypt_remote_upstream)
                        elif crypt_upstream_remote_type == "chunker":
                            return find_chunker_upstream(crypt_remote_upstream)
                        else:
                            log.warning(f'{crypt_remote_upstream} is an unsupported type: {rclone_remotes[crypt_remote_upstream]["type"]}.')
                            return []
                    except KeyError:
                        log.error(f'Upstream remote {crypt_remote_upstream} does not exist in rclone.')
                        exit(1)

                def find_chunker_upstream(chunker_remote):
                    chunker_remote_upstream = rclone_remotes[chunker_remote]['remote'].split(":")[0]
                    try:
                        chunker_upstream_remote_type = rclone_remotes[chunker_remote_upstream]['type']
                        if chunker_upstream_remote_type == "drive":
                            return [chunker_remote_upstream]
                        elif chunker_upstream_remote_type == "union":
                            return find_union_upstreams(chunker_remote_upstream)
                        elif chunker_upstream_remote_type == "crypt":
                            return find_crypt_upstream(chunker_remote_upstream)
                        else:
                            log.warning(f'{chunker_remote_upstream} is an unsupported type: {rclone_remotes[chunker_remote_upstream]["type"]}.')
                            return []
                    except KeyError:
                        log.error(f'Upstream remote {chunker_remote_upstream} does not exist in rclone.')
                        exit(1)

                def find_union_upstreams(union_remote):
                    union_parsed_upstream = []
                    for upstream_remote in rclone_remotes[union_remote]['upstreams'].split(' '):
                        remote_string = upstream_remote.split(":")[0]
                        try:
                            upstream_remote_type = rclone_remotes[remote_string]['type']
                            if upstream_remote_type == "drive":
                                union_parsed_upstream.append(upstream_remote.split(":")[0])
                            elif upstream_remote_type == "crypt":
                                union_parsed_upstream.extend(find_crypt_upstream(remote_string))
                            elif remote_type == "chunker":
                                union_parsed_upstream.extend(find_chunker_upstream(union_remote))
                            else:
                                log.warning(f'{remote_string} is an unsupported type: {rclone_remotes[remote_string]["type"]}.')
                        except KeyError:
                            log.error(f'Upstream remote {remote_string} does not exist in rclone.')
                            exit(1)
                    return union_parsed_upstream

                parsed_remotes = []
                try:
                    remote_type = rclone_remotes[config_remote]['type']
                    if remote_type == "crypt":
                        parsed_remotes.extend(find_crypt_upstream(config_remote))
                    elif remote_type == "chunker":
                        parsed_remotes.extend(find_chunker_upstream(config_remote))
                    elif remote_type == "drive":
                        parsed_remotes.append(config_remote)
                    elif remote_type == "union":
                        parsed_remotes.extend(find_union_upstreams(config_remote))
                    else:
                        log.warning(f'{config_remote} has an unsupported type: {rclone_remotes[config_remote]["type"]}.')

                except KeyError:
                    log.error(f'{config_remote} is an invalid remote.')
                    exit(1)

                finally:
                    log.debug(f"Parsed remotes: {parsed_remotes}")

                if parsed_remotes:
                    for remote in list(dict.fromkeys(parsed_remotes)):
                        remote_env = f'RCLONE_CONFIG_{remote.upper()}_SERVICE_ACCOUNT_FILE'
                        subprocess_env[remote_env] = self.service_account
                    log.debug(subprocess_env)
                else:
                    log.warning('No remotes were added to ENV.')

            extras = self.__extras2string()
            if len(extras) > 2:
                cmd += f' {extras}'
            excludes = self.__excludes2string()
            if len(excludes) > 2:
                cmd += f' {excludes}'
            if self.plex.get('enabled'):
                r = re.compile(r"https?://(www\.)?")
                rc_url = r.sub('', self.plex['rclone']['url']).strip().strip('/')
                cmd += f' --rc --rc-addr={cmd_quote(rc_url)}'
            if self.dry_run:
                cmd += ' --dry-run'

            # exec
            log.debug("Using: %s", cmd)
            return_code = process.execute(cmd, callback, subprocess_env)
            return True, return_code
        except Exception:
            log.exception("Exception occurred while uploading '%s' to remote: %s", self.config['upload_folder'],
                          self.name)
            return_code = 9999

        return False, return_code

    # internals
    def __extras2string(self):
        return ' '.join(f"{key}={cmd_quote(value) if isinstance(value, str) else value}" for (key, value) in
                        self.config['rclone_extras'].items()).replace('=None', '').strip()

    def __excludes2string(self):
        return ' '.join(
            "--exclude=%s" % (
                cmd_quote(glob.escape(value) if value.startswith(os.path.sep) else value) if isinstance(value,
                                                                                                        str) else value)
            for value in
            self.config['rclone_excludes']).replace('=None', '').strip()


class RcloneSyncer:
    def __init__(self, from_remote, to_remote, **kwargs):
        self.from_config = from_remote
        self.to_config = to_remote

        # trigger logic
        self.rclone_sleeps = misc.merge_dicts(self.from_config['rclone_sleeps'], self.to_config['rclone_sleeps'])
        self.trigger_tracks = {}
        self.delayed_check = 0
        self.delayed_trigger = None

        # parse rclone_extras from kwargs
        self.rclone_extras = kwargs.get('rclone_extras', {})
        # parse dry_run from kwargs
        self.dry_run = kwargs.get('dry_run', False)
        # parse use_copy from kwargs
        self.use_copy = kwargs.get('use_copy', False)

    def sync(self, cmd_wrapper):
        if not cmd_wrapper:
            log.error(
                "You must provide a cmd_wrapper method to wrap the rclone sync command for the desired sync agent")
            return False, self.delayed_check, self.delayed_trigger

        # build sync command
        cmd = f"rclone {'copy' if self.use_copy else 'sync'} {cmd_quote(self.from_config['sync_remote'])} {cmd_quote(self.to_config['sync_remote'])}"

        extras = self.__extras2string()
        if len(extras) > 2:
            cmd += f' {extras}'
        if self.dry_run:
            cmd += ' --dry-run'

        sync_agent_cmd = cmd_wrapper(cmd)
        log.debug("Using: %s", sync_agent_cmd)

        # exec
        process.execute(sync_agent_cmd, self._sync_logic)
        return not self.delayed_check, self.delayed_check, self.delayed_trigger

    # internals

    def _sync_logic(self, data):
        # loop sleep triggers
        for trigger_text, trigger_config in self.rclone_sleeps.items():
            # check/reset trigger timeout
            if (
                    trigger_text in self.trigger_tracks
                    and self.trigger_tracks[trigger_text]['expires'] != ''
                    and time.time() >= self.trigger_tracks[trigger_text]['expires']
            ):
                log.warning("Tracking of trigger: %r has expired, resetting occurrence count and timeout",
                            trigger_text)
                self.trigger_tracks[trigger_text] = {'count': 0, 'expires': ''}

            # check if trigger_text is in data
            if trigger_text.lower() in data.lower():
                # check / increase tracking count of trigger_text
                if trigger_text not in self.trigger_tracks or self.trigger_tracks[trigger_text]['count'] == 0:
                    # set initial tracking info for trigger
                    self.trigger_tracks[trigger_text] = {'count': 1, 'expires': time.time() + trigger_config['timeout']}
                    log.warning("Tracked first occurrence of trigger: %r. Expiring in %d seconds at %s", trigger_text,
                                trigger_config['timeout'], time.strftime('%Y-%m-%d %H:%M:%S',
                                                                         time.localtime(
                                                                             self.trigger_tracks[trigger_text][
                                                                                 'expires'])))
                else:
                    # trigger_text WAS seen before increase count
                    self.trigger_tracks[trigger_text]['count'] += 1
                    log.warning("Tracked trigger: %r has occurred %d/%d times within %d seconds", trigger_text,
                                self.trigger_tracks[trigger_text]['count'], trigger_config['count'],
                                trigger_config['timeout'])

                    # check if trigger_text was found the required amount of times to abort
                    if self.trigger_tracks[trigger_text]['count'] >= trigger_config['count']:
                        log.warning(
                            "Tracked trigger %r has reached the maximum limit of %d occurrences within %d seconds,"
                            " aborting upload...", trigger_text, trigger_config['count'], trigger_config['timeout'])
                        self.delayed_check = trigger_config['sleep']
                        self.delayed_trigger = trigger_text
                        return True
        return False

    def __extras2string(self):
        return ' '.join(f"{key}={cmd_quote(value) if isinstance(value, str) else value}" for (key, value) in
                        self.rclone_extras.items()).replace('=None', '').strip()


class RcloneThrottler:
    def __init__(self, url):
        self.url = url

    def validate(self):
        success = False
        payload = {'validated': True}
        try:
            resp = requests.post(urljoin(self.url, 'rc/noop'), json=payload, timeout=15, verify=False)
            if '{' in resp.text and '}' in resp.text:
                data = resp.json()
                success = data['validated']
        except Exception:
            log.exception("Exception validating rc url %s: ", self.url)
        return success

    def throttle_active(self, speed):
        if speed:
            try:
                resp = requests.post(urljoin(self.url, 'core/stats'), timeout=15, verify=False)
                if '{' in resp.text and '}' in resp.text:
                    data = resp.json()
                    if 'transferring' in data and len(data['transferring']) > 0:
                        # Sum total speed of all active transfers to determine if greater than current_speed
                        current_speed = sum(
                            float(transfer['speed'])
                            for transfer in data['transferring']
                        )

                        return (current_speed / 1000000) - 10 <= float(speed.rstrip('M'))
            except Exception:
                log.exception("Exception checking if throttle currently active")

        return False

    def throttle(self, speed):
        success = False
        payload = {'rate': speed}
        try:
            resp = requests.post(urljoin(self.url, 'core/bwlimit'), json=payload, timeout=15, verify=False)
            if '{' in resp.text and '}' in resp.text:
                data = resp.json()
                if 'error' in data:
                    log.error("Failed to throttle %s: %s", self.url, data['error'])
                elif 'rate' in data and speed in data['rate']:
                    log.warning("Successfully throttled %s to %s.", self.url, speed)
                    success = True

        except Exception:
            log.exception("Exception sending throttle request to %s: ", self.url)
        return success

    def no_throttle(self):
        success = False
        payload = {'rate': 'off'}
        try:
            resp = requests.post(urljoin(self.url, 'core/bwlimit'), json=payload, timeout=15, verify=False)
            if '{' in resp.text and '}' in resp.text:
                data = resp.json()
                if 'error' in data:
                    log.error("Failed to un-throttle %s: %s", self.url, data['error'])
                elif 'rate' in data and data['rate'] == 'off':
                    log.warning("Successfully un-throttled %s", self.url)
                    success = True
        except Exception:
            log.exception("Exception sending un-throttle request to %s: ", self.url)
        return success
