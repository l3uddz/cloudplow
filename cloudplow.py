#!/usr/bin/env python3
import logging
import time
from logging.handlers import RotatingFileHandler

import schedule

from utils import config, lock, path, decorators, version
from utils.notifications import Notifications
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

# Set schedule logger to ERROR
logging.getLogger('schedule').setLevel(logging.ERROR)

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
log = root_logger.getChild('cloudplow')

# Load config from disk
conf.load()

# Init Notifications class
notify = Notifications()

# Ensure lock folder exists
lock.ensure_lock_folder()

# Logic vars
uploader_delay = {}


############################################################
# MISC FUNCS
############################################################

def init_notifications():
    try:
        for notification_name, notification_config in conf.configs['notifications'].items():
            notify.load(**notification_config)
    except Exception:
        log.exception("Exception initializing notification agents: ")
    return


def check_suspended_uploaders(uploader_to_check=None):
    try:
        for uploader_name, suspension_expiry in uploader_delay.copy().items():
            # if uploader_to_check is given, only check this uploader
            if uploader_to_check and uploader_to_check != uploader_name:
                continue

            if time.time() < suspension_expiry:
                # this remote is still delayed due to a previous abort due to triggers
                use_logger = log.debug if not uploader_to_check else log.info
                use_logger(
                    "%s is still suspended due to a previously aborted upload. Normal operation in %d seconds at %s",
                    uploader_name, int(suspension_expiry - time.time()),
                    time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(suspension_expiry)))
                # return True when suspended if uploader_to_check is supplied
                if uploader_to_check:
                    return True
            else:
                log.warning("%s is no longer suspended due to a previous aborted upload!",
                            uploader_name)
                uploader_delay.pop(uploader_name, None)
                # send notification that remote is no longer timed out
                notify.send(message="Upload suspension has expired for remote: %s" % uploader_name)

    except Exception:
        log.exception("Exception checking suspended uploaders: ")
    return False


############################################################
# DOER FUNCS
############################################################

@decorators.timed
def do_upload(remote=None):
    lock_file = lock.upload()
    if lock_file.is_locked():
        log.info("Waiting for running upload to finish before proceeding...")

    with lock_file:
        log.info("Starting upload")
        try:
            # loop each supplied uploader config
            for uploader_remote, uploader_config in conf.configs['uploader'].items():
                # if remote is not None, skip this remote if it is not == remote
                if remote and uploader_remote != remote:
                    continue

                # retrieve rclone config for this remote
                rclone_config = conf.configs['remotes'][uploader_remote]

                # check if this remote is delayed
                if check_suspended_uploaders(uploader_remote):
                    continue

                # send notification that upload is starting
                notify.send(message="Upload of %d GB has begun for remote: %s" % (
                    path.get_size(rclone_config['upload_folder'], uploader_config['size_excludes']), uploader_remote))

                # perform the upload
                uploader = Uploader(uploader_remote, uploader_config, rclone_config, conf.configs['core']['dry_run'])
                resp, resp_trigger = uploader.upload()

                if resp:
                    # non 0 result indicates a trigger was met, the result is how many hours to sleep this remote for
                    log.info(
                        "Upload aborted due to trigger: %r being met, %s will continue automatic uploading normally in "
                        "%d hours", resp_trigger, uploader_remote, resp)

                    # add remote to uploader_delay
                    uploader_delay[uploader_remote] = time.time() + ((60 * 60) * resp)
                    # send aborted upload notification
                    notify.send(
                        message="Upload was aborted for remote: %s due to trigger %r, uploads suspended for %d hours" %
                                (uploader_remote, resp_trigger, resp))
                else:
                    # send successful upload notification
                    notify.send(message="Upload was completed successfully for remote: %s" % uploader_remote)

                # remove leftover empty directories from disk
                if not conf.configs['core']['dry_run']:
                    uploader.remove_empty_dirs()

        except Exception:
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
                    clean_resp, deleted_ok, deleted_fail = hidden.clean_remote(hidden_remote_name, hidden_remote_config)

                    # send notification
                    if deleted_ok or deleted_fail:
                        notify.send(message="Cleaned %d hidden(s) with %d failure(s) from remote: %s" % (
                            deleted_ok, deleted_fail, hidden_remote_name))

                # remove the HIDDEN~ files from disk and empty directories from unionfs-fuse folder
                if not conf.configs['core']['dry_run']:
                    hidden.remove_local_hidden()
                    hidden.remove_empty_dirs()

        except Exception:
            log.exception("Exception occurred while cleaning hiddens: ")

    log.info("Finished hidden cleaning")


############################################################
# SCHEDULED FUNCS
############################################################

def scheduled_uploader(uploader_name, uploader_settings):
    log.debug("Checking used disk space for uploader: %s", uploader_name)
    try:
        rclone_settings = conf.configs['remotes'][uploader_name]

        # check suspended uploaders
        check_suspended_uploaders()

        # check used disk space
        used_space = path.get_size(rclone_settings['upload_folder'], uploader_settings['size_excludes'])

        # if disk space is above the limit, clean hidden files then upload
        if used_space >= uploader_settings['max_size_gb']:
            log.info("Uploader: %s. Local folder size is currently %d GB over the maximum limit of %d GB",
                     uploader_name, used_space - uploader_settings['max_size_gb'], uploader_settings['max_size_gb'])

            # clean hidden files
            do_hidden()
            # upload
            do_upload(uploader_name)

        else:
            log.info(
                "Uploader: %s. Local folder size is currently %d GB. "
                "Still have %d GB remaining before its eligible to begin uploading...",
                uploader_name, used_space, uploader_settings['max_size_gb'] - used_space)

    except Exception:
        log.exception("Unexpected exception occurred while processing uploader %s: ", uploader_name)


############################################################
# MAIN
############################################################

if __name__ == "__main__":
    # show latest version info from git
    version.check_version()

    # run chosen mode
    try:
        # init notifications
        init_notifications()

        if conf.args['cmd'] == 'clean':
            log.info("Started in clean mode")
            do_hidden()
        elif conf.args['cmd'] == 'upload':
            log.info("Started in upload mode")
            do_hidden()
            do_upload()
        elif conf.args['cmd'] == 'run':
            log.info("Started in run mode")

            # add uploader to schedule
            for uploader, uploader_conf in conf.configs['uploader'].items():
                schedule.every(uploader_conf['check_interval']).minutes.do(scheduled_uploader, uploader, uploader_conf)
                log.info("Added %s uploader to schedule, checking available disk space every %d minutes", uploader,
                         uploader_conf['check_interval'])

            # run schedule
            while True:
                try:
                    schedule.run_pending()
                except Exception:
                    log.exception("Unhandled exception occurred while processing scheduled tasks: ")
                time.sleep(1)
        else:
            log.error("Unknown command: %r", conf.args['cmd'])

    except KeyboardInterrupt:
        log.info("cloudplow was interrupted by Ctrl + C")
    except Exception:
        log.exception("Unexpected fatal exception occurred: ")
