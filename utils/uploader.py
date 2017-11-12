import logging

from . import path
from .rclone import Rclone

log = logging.getLogger("uploader")


class Uploader:
    def __init__(self, name, uploader_config, rclone_config, dry_run):
        self.name = name
        self.uploader_config = uploader_config
        self.rclone_config = rclone_config
        self.dry_run = dry_run
        self.rclone = Rclone(name, rclone_config, dry_run)

    def upload(self):
        log.info("Uploading '%s' to remote: %s", self.rclone_config['upload_folder'], self.name)
        resp = self.rclone.upload(self.__upload_logic)
        log.info("Finished uploading to remote: %s", self.name)
        return resp

    def remove_empty_dirs(self):
        path.remove_empty_dirs(self.rclone_config['upload_folder'], self.rclone_config['remove_empty_dir_depth'])
        log.info("Removed empty directories from '%s' with mindepth: %d", self.rclone_config['upload_folder'],
                 self.rclone_config['remove_empty_dir_depth'])
        return

    # internals
    def __upload_logic(self, data):
        log.debug("Logic processing: %s", data)
        return False
