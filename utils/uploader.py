import logging
import glob
import time

from . import path
from .rclone import RcloneUploader

log = logging.getLogger("uploader")


class Uploader:
    def __init__(self, name, uploader_config, rclone_config, rclone_binary_path, rclone_config_path, plex, dry_run):
        self.name = name
        self.uploader_config = uploader_config
        self.rclone_config = rclone_config
        self.trigger_tracks = {}
        self.delayed_check = 0
        self.delayed_trigger = None
        self.rclone_binary_path = rclone_binary_path
        self.rclone_config_path = rclone_config_path
        self.plex = plex
        self.dry_run = dry_run
        self.service_account = None

    def set_service_account(self, sa_file):
        self.service_account = sa_file
        log.info(f"Using service account: {sa_file}")

    def upload(self):
        rclone_config = self.rclone_config.copy()

        # should we exclude open files
        if self.uploader_config['exclude_open_files']:
            files_to_exclude = self.__opened_files()
            if len(files_to_exclude):
                log.info(f"Excluding these files from being uploaded because they were open: {files_to_exclude}")
                # add files_to_exclude to rclone_config
                for item in files_to_exclude:
                    rclone_config['rclone_excludes'].append(glob.escape(item))

        # do upload
        if self.service_account is not None:
            rclone = RcloneUploader(self.name, rclone_config, self.rclone_binary_path, self.rclone_config_path,
                                    self.plex, self.dry_run, self.service_account)
        else:
            rclone = RcloneUploader(self.name, rclone_config, self.rclone_binary_path, self.rclone_config_path,
                                    self.plex, self.dry_run)

        log.info(f"Uploading '{rclone_config['upload_folder']}' to remote: {self.name}")
        self.delayed_check = 0
        self.delayed_trigger = None
        self.trigger_tracks = {}
        upload_status, return_code = rclone.upload(self.__logic)
        if return_code == 7:
            log.info("Received 'Max Transfer Reached' signal from Rclone.")
            self.delayed_trigger = "Rclone's 'Max Transfer Reached' signal"
            self.delayed_check = 25
        
        log.debug("return_code is: %s", return_code)
        if upload_status and return_code == 0:
            log.info(f"Finished uploading to remote: {self.name}")
        else:
            return

        return self.delayed_check, self.delayed_trigger

    def remove_empty_dirs(self):
        path.remove_empty_dirs(self.rclone_config['upload_folder'], self.rclone_config['remove_empty_dir_depth'])
        log.info(f"Removed empty directories from '{self.rclone_config['upload_folder']}' with min depth: {self.rclone_config['remove_empty_dir_depth']}")
        return

    # internals
    def __opened_files(self):
        open_files = path.opened_files(self.rclone_config['upload_folder'])
        return [
            item.replace(self.rclone_config['upload_folder'], '')
            for item in open_files
            if not self.__is_opened_file_excluded(item)
        ]

    def __is_opened_file_excluded(self, file_path):
        return any(
            item.lower() in file_path.lower()
            for item in self.uploader_config['opened_excludes']
        )

    def __logic(self, data):
        # loop sleep triggers
        for trigger_text, trigger_config in self.rclone_config['rclone_sleeps'].items():
            # check/reset trigger timeout
            if (
                trigger_text in self.trigger_tracks
                and self.trigger_tracks[trigger_text]['expires'] != ''
                and time.time() >= self.trigger_tracks[trigger_text]['expires']
            ):
                log.warning(f"Tracking of trigger: {trigger_text} has expired, resetting occurrence count and timeout")
                self.trigger_tracks[trigger_text] = {'count': 0, 'expires': ''}

            # check if trigger_text is in data
            if trigger_text.lower() in data.lower():
                # check / increase tracking count of trigger_text
                if trigger_text not in self.trigger_tracks or self.trigger_tracks[trigger_text]['count'] == 0:
                    # set initial tracking info for trigger
                    self.trigger_tracks[trigger_text] = {'count': 1, 'expires': time.time() + trigger_config['timeout']}
                    log.warning(f"Tracked first occurrence of trigger: {trigger_text}. Expiring in {trigger_config['timeout']} seconds at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.trigger_tracks[trigger_text]['expires']))}")
                else:
                    # trigger_text WAS seen before increase count
                    self.trigger_tracks[trigger_text]['count'] += 1
                    log.warning(f"Tracked trigger: {trigger_text} has occurred {self.trigger_tracks[trigger_text]['count']}/{trigger_config['count']} times within {trigger_config['timeout']} seconds")

                    # check if trigger_text was found the required amount of times to abort
                    if self.trigger_tracks[trigger_text]['count'] >= trigger_config['count']:
                        log.warning(f"Tracked trigger {trigger_text} has reached the maximum limit of {trigger_config['count']} occurrences within {trigger_config['timeout']} seconds, aborting upload...")
                        self.delayed_check = trigger_config['sleep']
                        self.delayed_trigger = trigger_text
                        return True
        return False
