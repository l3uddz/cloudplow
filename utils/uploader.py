import logging
import re
import time

from . import path
from .rclone import RcloneUploader

log = logging.getLogger("uploader")


class Uploader:
    def __init__(self, name, uploader_config, rclone_config, dry_run, rclone_binary_path, rclone_config_path, use_rc):
        self.name = name
        self.uploader_config = uploader_config
        self.rclone_config = rclone_config
        self.dry_run = dry_run
        self.trigger_tracks = {}
        self.delayed_check = 0
        self.delayed_trigger = None
        self.rclone_binary_path = rclone_binary_path
        self.rclone_config_path = rclone_config_path
        self.use_rc = use_rc

    def set_service_account(self,file):
        self.service_account = file
        log.info("SERVICE ACCOUNT SET TO: %s" % self.service_account)

    def upload(self):
        rclone_config = self.rclone_config.copy()

        # should we exclude open files
        if self.uploader_config['exclude_open_files']:
            files_to_exclude = self.__opened_files()
            if len(files_to_exclude):
                log.info("Excluding these files from being uploaded because they were open: %r", files_to_exclude)
                # add files_to_exclude to rclone_config
                for item in files_to_exclude:
                    rclone_config['rclone_excludes'].append(re.escape(item))

        # do upload
        if self.service_account != None:
            log.info("INITIALIZING UPLOADER WITH SERVICE_ACCOUNT %s" % self.service_account)
            rclone = RcloneUploader(self.name, rclone_config, self.rclone_binary_path, self.rclone_config_path,
                                    self.dry_run, self.use_rc, self.service_account)
        else:
            rclone = RcloneUploader(self.name, rclone_config, self.rclone_binary_path, self.rclone_config_path,
                                    self.dry_run, self.use_rc)
        log.info("Uploading '%s' to remote: %s", rclone_config['upload_folder'], self.name)
        rclone.upload(self.__logic)
        log.info("Finished uploading to remote: %s", self.name)
        return self.delayed_check, self.delayed_trigger

    def remove_empty_dirs(self):
        path.remove_empty_dirs(self.rclone_config['upload_folder'], self.rclone_config['remove_empty_dir_depth'])
        log.info("Removed empty directories from '%s' with mindepth: %d", self.rclone_config['upload_folder'],
                 self.rclone_config['remove_empty_dir_depth'])
        return

    # internals
    def __opened_files(self):
        open_files = path.opened_files(self.rclone_config['upload_folder'])
        rclone_excludes = []
        for item in open_files:
            if not self.__is_opened_file_excluded(item):
                rclone_excludes.append(item.replace(self.rclone_config['upload_folder'], ''))
        return rclone_excludes

    def __is_opened_file_excluded(self, file_path):
        for item in self.uploader_config['opened_excludes']:
            if item.lower() in file_path.lower():
                return True
        return False

    def __logic(self, data):
        # loop sleep triggers
        for trigger_text, trigger_config in self.rclone_config['rclone_sleeps'].items():
            # check/reset trigger timeout
            if trigger_text in self.trigger_tracks and self.trigger_tracks[trigger_text]['expires'] != '':
                if time.time() >= self.trigger_tracks[trigger_text]['expires']:
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
