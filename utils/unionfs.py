import concurrent.futures
import logging

from . import path
from .rclone import RcloneUploader

log = logging.getLogger('unionfs')


class UnionfsHiddenFolder:
    def __init__(self, hidden_folder, dry_run, rclone_binary_path, rclone_config_path):
        self.unionfs_fuse = hidden_folder
        self.dry_run = dry_run
        self.hidden_files = self.__files()
        self.hidden_folders = self.__folders()
        self.rclone_binary_path = rclone_binary_path
        self.rclone_config_path = rclone_config_path

    def clean_remote(self, name, remote):
        """
        Delete hidden_files and hidden_folders from remote

        :param name: name of the rclone remote
        :param remote: rclone remote item from config.json
        :return: True or False based on whether or not clean was successful
        """
        delete_success = 0
        delete_failed = 0

        try:
            rclone = RcloneUploader(name, remote, self.rclone_binary_path, self.rclone_config_path, self.dry_run)
            # clean hidden files from remote using threadpool
            if self.hidden_files:
                with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                    log.info("Cleaning %d hidden file(s) from remote: %s", len(self.hidden_files), name)
                    future_to_remote_file = {}
                    for hidden_file in self.hidden_files:
                        remote_file = self.__hidden2remote(remote, hidden_file)
                        if remote_file:
                            future_to_remote_file[executor.submit(rclone.delete_file, remote_file)] = remote_file
                        else:
                            log.error("Failed mapping file '%s' to a remote file", hidden_file)
                            delete_failed += 1

                    for future in concurrent.futures.as_completed(future_to_remote_file):
                        remote_file = future_to_remote_file[future]
                        try:
                            if future.result():
                                log.info("Removed file '%s'", remote_file)
                                delete_success += 1
                            else:
                                log.error("Failed removing file '%s'", remote_file)
                                delete_failed += 1
                        except Exception:
                            log.exception("Exception processing result from rclone delete file future for '%s': ",
                                          remote_file)
                            delete_failed += 1

            # clean hidden folders from remote
            if self.hidden_folders:
                log.info("Cleaning %d hidden folder(s) from remote: %s", len(self.hidden_folders), name)
                for hidden_folder in self.hidden_folders:
                    remote_folder = self.__hidden2remote(remote, hidden_folder)
                    if remote_folder and rclone.delete_folder(remote_folder):
                        log.info("Removed folder '%s'", remote_folder)
                        delete_success += 1
                    else:
                        log.error("Failed removing folder '%s'", remote_folder)
                        delete_failed += 1

            if self.hidden_folders or self.hidden_files:
                log.info("Completed cleaning hidden(s) from remote: %s", name)
                log.info("%d items were deleted, %d items failed to delete", delete_success, delete_failed)

            return True, delete_success, delete_failed

        except Exception:
            log.exception("Exception cleaning hidden(s) from %r: ", self.unionfs_fuse)

        return False, delete_success, delete_failed

    def remove_local_hidden(self):
        if len(self.hidden_files):
            path.delete(self.hidden_files)
            log.info("Removed %d local hidden file(s) from disk", len(self.hidden_files))
        if len(self.hidden_folders):
            path.delete(self.hidden_folders)
            log.info("Removed %d local hidden folder(s) from disk", len(self.hidden_folders))
        return

    def remove_empty_dirs(self):
        path.remove_empty_dirs(self.unionfs_fuse, 1)
        log.info("Removed empty directories from '%s'", self.unionfs_fuse)

    # internals
    def __files(self):
        hidden_files = []
        try:
            hidden_files = path.find_files(self.unionfs_fuse, '_HIDDEN~')
            log.info("Found %d hidden files in %r", len(hidden_files), self.unionfs_fuse)
        except Exception:
            log.exception("Exception finding hidden files for %r: ", self.unionfs_fuse)
            hidden_files = None
        return hidden_files

    def __folders(self):
        hidden_folders = []
        try:
            hidden_folders = path.find_folders(self.unionfs_fuse, '_HIDDEN~')
            log.info("Found %d hidden folders in %r", len(hidden_folders), self.unionfs_fuse)
        except Exception:
            log.exception("Exception finding hidden folders for %r: ", self.unionfs_fuse)
            hidden_folders = None
        return hidden_folders

    def __hidden2remote(self, remote, hidden_path):
        try:
            remote_path = hidden_path.replace(self.unionfs_fuse, remote['hidden_remote']).rstrip('_HIDDEN~')
            log.debug("Mapped '%s' to '%s'", hidden_path, remote_path)
            return remote_path
        except Exception:
            log.exception("Exception mapping hidden file '%s' to its rclone remote path", hidden_path)
        return None
