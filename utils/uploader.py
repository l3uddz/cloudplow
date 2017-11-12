import logging
import time

from . import path
from .rclone import Rclone

log = logging.getLogger("uploader")


class Uploader:
    def __init__(self, name, uploader_config, rclone_config, dry_run):
        self.name = name
        self.uploader_config = uploader_config
        self.rclone_config = rclone_config
        self.dry_run = dry_run
        self.trigger_tracks = {}
        self.delayed_check = 0
        self.rclone = Rclone(name, rclone_config, dry_run)

    def upload(self):
        log.info("Uploading '%s' to remote: %s", self.rclone_config['upload_folder'], self.name)
        self.rclone.upload(self.__logic)
        log.info("Finished uploading to remote: %s", self.name)
        return self.delayed_check

    def remove_empty_dirs(self):
        path.remove_empty_dirs(self.rclone_config['upload_folder'], self.rclone_config['remove_empty_dir_depth'])
        log.info("Removed empty directories from '%s' with mindepth: %d", self.rclone_config['upload_folder'],
                 self.rclone_config['remove_empty_dir_depth'])
        return

    # internals
    def __logic(self, data):
        # loop sleep triggers
        for trigger_text, trigger_config in self.rclone_config['rclone_sleep'].items():
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
                    log.warning("Tracked trigger: %r has occurred %d/%d times", trigger_text,
                                self.trigger_tracks[trigger_text]['count'], trigger_config['count'])
                    # check if trigger_text was found the required amount of times to abort
                    if self.trigger_tracks[trigger_text]['count'] >= trigger_config['count']:
                        log.warning(
                            "Tracked trigger %r has reached the maximum limit of %d occurrences within %d seconds,"
                            " aborting upload...", trigger_text, trigger_config['count'], trigger_config['timeout'])
                        self.delayed_check = trigger_config['sleep']
                        return True
        return False
