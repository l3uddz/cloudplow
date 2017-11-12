import logging

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

    def __upload_logic(self, data):
        log.debug("Logic processing: %s", data)
        return False
