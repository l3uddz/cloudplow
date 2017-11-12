#!/usr/bin/env python3
import logging
import time
from logging.handlers import RotatingFileHandler

from utils import config, lock
from utils import decorators
from utils.unionfs import UnionfsHiddenFolder
from utils.uploader import Uploader

############################################################
# INIT
############################################################

# Logging
log_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)-10s - %(name)-20s -  %(funcName)-30s- %(message)s')
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Set console logger
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

# Init config
conf = config.Config()

# Set file logger
file_handler = RotatingFileHandler(
    conf.settings['logfile'],
    maxBytes=1024 * 1024 * 5,
    backupCount=5
)
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

# Set chosen logging level
root_logger.setLevel(conf.settings['loglevel'])
log = root_logger.getChild('cloud_plow')

# Load config from disk
conf.load()

# Ensure lock folder exists
lock.ensure_lock_folder()

# Logic vars
uploader_delay = {}


############################################################
# DOER FUNCS
############################################################

@decorators.timed
def do_upload():
    lock_file = lock.upload()
    if lock_file.is_locked():
        log.info("Waiting for running upload to finish before proceeding...")

    with lock_file:
        log.info("Starting upload")
        try:
            # loop each supplied uploader config
            for uploader_remote, uploader_config in conf.configs['uploader'].items():
                # retrieve rclone config for this remote
                rclone_config = conf.configs['remotes'][uploader_remote]
                # check if this remote is delayed
                if uploader_remote in uploader_delay:
                    if time.time() < uploader_delay[uploader_remote]:
                        # this remote is still delayed due to a previous abort due to triggers
                        log.warning(
                            "%s is delayed due to a previously aborted upload. Normal operation in %d seconds at %s",
                            uploader_remote, int(uploader_delay[uploader_remote] - time.time()),
                            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(uploader_delay[uploader_remote])))
                        continue
                    else:
                        log.warning("%s is no longer delayed due to a previous aborted upload, proceeding!",
                                    uploader_remote)
                        uploader_delay.pop(uploader_remote, None)

                # perform the upload
                uploader = Uploader(uploader_remote, uploader_config, rclone_config, conf.configs['core']['dry_run'])
                resp = uploader.upload()
                if resp:
                    # non 0 result indicates a trigger was met, the result is how many hours to sleep this remote for
                    log.warning(
                        "Upload aborted due to triggers being met, %s will continue automatic uploading normally in "
                        "%d hours", uploader_remote, resp)
                    # add remote to uploader_delay
                    uploader_delay[uploader_remote] = time.time() + ((60 * 60) * resp)

                # remove leftover empty directories from disk
                if not conf.configs['core']['dry_run']:
                    uploader.remove_empty_dirs()

        except:
            log.exception("Exception occurred while uploading: ")

    log.info("Finished upload")


@decorators.timed
def do_sync():
    lock_file = lock.sync()
    if lock_file.is_locked():
        log.info("Waiting for running sync to finish before proceeding...")

    with lock_file:
        log.info("Starting sync")
        time.sleep(10)

    log.info("Finished sync")


@decorators.timed
def do_hidden():
    lock_file = lock.hidden()
    if lock_file.is_locked():
        log.info("Waiting for running hidden cleaner to finish before proceeding...")

    with lock_file:
        log.info("Starting hidden cleaning")
        try:
            # loop each supplied hidden folder
            for hidden_folder, hidden_config in conf.configs['hidden'].items():
                hidden = UnionfsHiddenFolder(hidden_folder, conf.configs['core']['dry_run'])

                # loop the chosen remotes for this hidden config cleaning files
                for hidden_remote_name in hidden_config['hidden_remotes']:
                    # retrieve rclone config for this remote
                    hidden_remote_config = conf.configs['remotes'][hidden_remote_name]
                    # clean remote
                    hidden.clean_remote(hidden_remote_name, hidden_remote_config)

                # remove the HIDDEN~ files from disk and empty directories from unionfs-fuse folder
                if not conf.configs['core']['dry_run']:
                    hidden.remove_local_hidden()
                    hidden.remove_empty_dirs()

        except:
            log.exception("Exception occurred while cleaning hiddens: ")

    log.info("Finished hidden cleaning")


############################################################
# LOGIC FUNCS
############################################################


############################################################
# MAIN
############################################################

if __name__ == "__main__":
    # show latest version info from git

    # do chosen mode
    if conf.args['cmd'] == 'clean':
        do_hidden()
    elif conf.args['cmd'] == 'upload':
        do_upload()
    elif conf.args['cmd'] == 'run':
        log.info("Starting in longrunning mode")
    else:
        log.error("Unknown command: %r", conf.args['cmd'])
