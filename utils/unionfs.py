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
        :return: True or False based on whether clean was successful
        """
        delete_success = 0
        delete_failed = 0

        try:
            rclone = RcloneUploader(name, remote, self.rclone_binary_path, self.rclone_config_path, self.dry_run)
            # clean hidden files from remote using threadpool
            if self.hidden_files:
                with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                    log.info(f"Cleaning {len(self.hidden_files)} hidden file(s) from remote: {name}")
                    future_to_remote_file = {}
                    for hidden_file in self.hidden_files:
                        remote_file = self.__hidden2remote(remote, hidden_file)
                        if remote_file:
                            future_to_remote_file[executor.submit(rclone.delete_file, remote_file)] = remote_file
                        else:
                            log.error(f"Failed mapping file '{hidden_file}' to a remote file")
                            delete_failed += 1

                    for future in concurrent.futures.as_completed(future_to_remote_file):
                        remote_file = future_to_remote_file[future]
                        try:
                            if future.result():
                                log.info(f"Removed file '{remote_file}'")
                                delete_success += 1
                            else:
                                log.error(f"Failed removing file '{remote_file}'")
                                delete_failed += 1
                        except Exception:
                            log.exception("Exception processing result from rclone delete file future for '{remote_file}': ")
                            delete_failed += 1

            # clean hidden folders from remote
            if self.hidden_folders:
                log.info(f"Cleaning {len(self.hidden_folders)} hidden folder(s) from remote: {name}")
                for hidden_folder in self.hidden_folders:
                    remote_folder = self.__hidden2remote(remote, hidden_folder)
                    if remote_folder and rclone.delete_folder(remote_folder):
                        log.info(f"Removed folder '{remote_folder}'")
                        delete_success += 1
                    else:
                        log.error(f"Failed removing folder '{remote_folder}'")
                        delete_failed += 1

            if self.hidden_folders or self.hidden_files:
                log.info(f"Completed cleaning hidden(s) from remote: {name}")
                log.info(f"{delete_success} items were deleted, {delete_failed} items failed to delete")

            return True, delete_success, delete_failed

        except Exception:
            log.exception(f"Exception cleaning hidden(s) from {self.unionfs_fuse}: ")

        return False, delete_success, delete_failed

    def remove_local_hidden(self):
        if len(self.hidden_files):
            path.delete(self.hidden_files)
            log.info(f"Removed {len(self.hidden_files)} local hidden file(s) from disk")
        if len(self.hidden_folders):
            path.delete(self.hidden_folders)
            log.info(f"Removed {len(self.hidden_folders)} local hidden folder(s) from disk")
        return

    def remove_empty_dirs(self):
        path.remove_empty_dirs(self.unionfs_fuse, 1)
        log.info(f"Removed empty directories from '{self.unionfs_fuse}'")

    # internals
    def __files(self):
        hidden_files = []
        try:
            hidden_files = path.find_items(self.unionfs_fuse, '_HIDDEN~')
            log.info(f"Found {len(hidden_files)} hidden files in {self.unionfs_fuse}")
        except Exception:
            log.exception(f"Exception finding hidden files for {self.unionfs_fuse}: ")
            hidden_files = None
        return hidden_files

    def __folders(self):
        try:
            hidden_folders = path.find_items(self.unionfs_fuse, '_HIDDEN~')
            log.info(f"Found {len(hidden_folders)} hidden folders in {self.unionfs_fuse}")
        except Exception:
            log.exception(f"Exception finding hidden folders for {self.unionfs_fuse}: ")
            hidden_folders = None
        return hidden_folders

    def __hidden2remote(self, remote, hidden_path):
        try:
            remote_path = hidden_path.replace(self.unionfs_fuse, remote['hidden_remote']).rstrip('_HIDDEN~')
            log.debug(f"Mapped '{hidden_path}' to '{remote_path}'")
            return remote_path
        except Exception:
            log.exception(f"Exception mapping hidden file '{hidden_path}' to its rclone remote path")
        return None
