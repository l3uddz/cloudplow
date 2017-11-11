#!/usr/bin/env python3
import logging
import time
from logging.handlers import RotatingFileHandler

from utils import config, lock
from utils.rclone import Rclone
from utils.unionfs import UnionfsHiddenFolder

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

def do_upload():
    lock_file = lock.upload()
    if lock_file.is_locked():
        log.info("Waiting for running upload to finish before proceeding...")

    with lock_file:
        log.info("Starting upload")
        time.sleep(10)

    log.info("Finished upload")


def do_sync():
    lock_file = lock.sync()
    if lock_file.is_locked():
        log.info("Waiting for running sync to finish before proceeding...")

    with lock_file:
        log.info("Starting sync")
        time.sleep(10)

    log.info("Finished sync")


def do_hidden():
    lock_file = lock.hidden()
    if lock_file.is_locked():
        log.info("Waiting for running hidden cleaner to finish before proceeding...")

    with lock_file:
        log.info("Starting hidden cleaning")
        try:
            # loop each supplied hidden folder
            for hidden_folder, hidden_config in conf.configs['unionfs'].items():
                hidden = UnionfsHiddenFolder(hidden_folder)

                # loop the chosen remotes for this hidden config cleaning files
                for hidden_remote_name in hidden_config['hidden_remotes']:
                    # retrieve rclone config for this remote
                    hidden_remote_config = conf.configs['remotes'][hidden_remote_name]
                    # clean remote
                    hidden.clean_remote(hidden_remote_name, hidden_remote_config)

                # remove the HIDDEN~ files from disk
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
    do_hidden()
    exit(0)

    log.info("Starting...")
    log.debug("lol")
    test = Rclone('google', conf.configs['remotes']['google'], True)
    log.debug(test.extras)

    hidden_folder = UnionfsHiddenFolder('Y:\\Shared Videos\\TV')
    hidden_folder.clean_remote('google', conf.configs['remotes']['google'])
    hidden_folder.clean_remote('dropbox', conf.configs['remotes']['dropbox'])
    hidden_folder.remove_local_hidden()
