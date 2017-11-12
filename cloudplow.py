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
                # perform the upload
                uploader = Uploader(uploader_remote, uploader_config, rclone_config, conf.configs['core']['dry_run'])
                uploader.upload()
                # remove leftover empty directories from disk
                if not conf.configs['core']['dry_run']:
                    pass

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

                # remove the HIDDEN~ files from disk
                if not conf.configs['core']['dry_run']:
                    hidden.remove_local_hidden()
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
