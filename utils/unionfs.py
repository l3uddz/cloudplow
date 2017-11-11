import logging

from . import path

log = logging.getLogger('unionfs')


class UnionfsHiddenFolder:
    def __init__(self, hidden_folder):
        self.unionfs_fuse = hidden_folder
        self.hidden_files = self.__files()
        self.hidden_folders = self.__folders()

    def clean_remote(self, name, remote):
        """
        Delete hidden_files and hidden_folders from remote

        :param name: name of the rclone remote
        :param remote: rclone remote item from config.json
        :return: True or False based on whether or not clean was successful
        """

        try:
            # clean hidden files from remote
            if self.hidden_files:
                log.info("Cleaning %d hidden file(s) from remote: %s", len(self.hidden_files), name)
                for hidden_file in self.hidden_files:
                    remote_file = self.__hidden2remote(remote, hidden_file)
                    if remote_file:
                        log.info("Removing file '%s'", remote_file)

            # clean hidden folders from remote
            if self.hidden_folders:
                log.info("Cleaning %d hidden folder(s) from remote: %s", len(self.hidden_folders), name)
                for hidden_folder in self.hidden_folders:
                    remote_folder = self.__hidden2remote(remote, hidden_folder)
                    if remote_folder:
                        log.info("Removing folder '%s'", remote_folder)

            return True
        except:
            log.exception("Exception cleaning hidden(s) from %r: ", self.unionfs_fuse)
        return False

    def remove_local_hidden(self):
        if len(self.hidden_files):
            path.delete(self.hidden_files)
            log.info("Removed %d local hidden file(s)", len(self.hidden_files))
        if len(self.hidden_folders):
            path.delete(self.hidden_folders)
            log.info("Removed %d local hidden folder(s)", len(self.hidden_folders))
        return

    # internals
    def __files(self):
        hidden_files = []
        try:
            hidden_files = path.find_files(self.unionfs_fuse, '_HIDDEN~')
            log.info("Found %d hidden files in %r", len(hidden_files), self.unionfs_fuse)
        except:
            log.exception("Exception finding hidden files for %r: ", self.unionfs_fuse)
            hidden_files = None
        return hidden_files

    def __folders(self):
        hidden_folders = []
        try:
            hidden_folders = path.find_folders(self.unionfs_fuse, '_HIDDEN~')
            log.info("Found %d hidden folders in %r", len(hidden_folders), self.unionfs_fuse)
        except:
            log.exception("Exception finding hidden folders for %r: ", self.unionfs_fuse)
            hidden_folders = None
        return hidden_folders

    def __hidden2remote(self, remote, hidden_path):
        try:
            remote_path = hidden_path.replace(self.unionfs_fuse, remote['hidden_remote']).rstrip('_HIDDEN~')
            log.debug("Mapped '%s' to '%s'", hidden_path, remote_path)
            return remote_path
        except:
            log.exception("Exception mapping hidden file '%s' to its rclone remote path", hidden_path)
        return None
