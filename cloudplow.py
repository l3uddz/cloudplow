#!/usr/bin/env python3
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from multiprocessing import Manager, Process

import schedule

from utils import config, lock, path, decorators, version, misc
from utils.notifications import Notifications
from utils.syncer import Syncer
from utils.unionfs import UnionfsHiddenFolder
from utils.uploader import Uploader

############################################################
# INIT
############################################################

# Logging
log_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)-10s - %(name)-20s - %(funcName)-30s - %(message)s')
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Set schedule logger to ERROR
logging.getLogger('schedule').setLevel(logging.ERROR)

# Set console logger
console_handler = logging.StreamHandler(sys.stdout)
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

# Init Syncer class
syncer = Syncer(conf.configs)

# Ensure lock folder exists
lock.ensure_lock_folder()

# Logic vars
uploader_delay = None
syncer_delay = None


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


def init_syncers():
    try:
        for syncer_name, syncer_config in conf.configs['syncer'].items():
            # remove irrelevant parameters before loading syncer agent
            filtered_config = syncer_config.copy()
            filtered_config.pop('sync_interval', None)
            # load syncer agent
            syncer.load(**filtered_config)
    except Exception:
        log.exception("Exception initializing syncer agents: ")


def check_suspended_uploaders(uploader_to_check=None):
    suspended = False
    try:
        for uploader_name, suspension_expiry in uploader_delay.copy().items():
            if time.time() < suspension_expiry:
                # this remote is still delayed due to a previous abort due to triggers
                use_logger = log.debug if not (uploader_to_check and uploader_name == uploader_to_check) else log.info
                use_logger(
                    "%s is still suspended due to a previously aborted upload. Normal operation in %s at %s",
                    uploader_name, misc.seconds_to_string(int(suspension_expiry - time.time())),
                    time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(suspension_expiry)))
                # return True when suspended if uploader_to_check is supplied and this is that remote
                if uploader_to_check and uploader_name == uploader_to_check:
                    suspended = True
            else:
                log.warning("%s is no longer suspended due to a previous aborted upload!",
                            uploader_name)
                uploader_delay.pop(uploader_name, None)
                # send notification that remote is no longer timed out
                notify.send(message="Upload suspension has expired for remote: %s" % uploader_name)

    except Exception:
        log.exception("Exception checking suspended uploaders: ")
    return suspended


def check_suspended_syncers(syncers_delays, syncer_to_check=None):
    suspended = False
    try:
        for syncer_name, suspension_expiry in syncers_delays.copy().items():
            if time.time() < suspension_expiry:
                # this syncer is still delayed due to a previous abort due to triggers
                use_logger = log.debug if not (syncer_to_check and syncer_name == syncer_to_check) else log.info
                use_logger(
                    "%s is still suspended due to a previously aborted sync. Normal operation in %s at %s",
                    syncer_name, misc.seconds_to_string(int(suspension_expiry - time.time())),
                    time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(suspension_expiry)))
                # return True when suspended if syncer_to_check is supplied and this is that remote
                if syncer_to_check and syncer_name == syncer_to_check:
                    suspended = True
            else:
                log.warning("%s is no longer suspended due to a previous aborted sync!",
                            syncer_name)
                syncers_delays.pop(syncer_name, None)
                # send notification that remote is no longer timed out
                notify.send(message="Sync suspension has expired for syncer: %s" % syncer_name)

    except Exception:
        log.exception("Exception checking suspended syncers: ")
    return suspended


def run_process(task, manager_dict, **kwargs):
    try:
        new_process = Process(target=task, args=(manager_dict,), kwargs=kwargs)
        return new_process.start()
    except Exception:
        log.exception("Exception starting process with kwargs=%r: ", kwargs)


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
                        message="Upload was aborted for remote: %s due to trigger %r. Uploads suspended for %d hours" %
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
def do_sync(use_syncer=None, syncer_delays=syncer_delay):
    lock_file = lock.sync()
    if lock_file.is_locked():
        log.info("Waiting for running sync to finish before proceeding...")

    with lock_file:
        log.info("Starting sync")
        try:
            for sync_name, sync_config in conf.configs['syncer'].items():
                # if syncer is not None, skip this syncer if not == syncer
                if use_syncer and sync_name != use_syncer:
                    continue

                # send notification that sync is starting
                notify.send(message='Sync initiated for syncer: %s. %s %s instance...' % (
                    sync_name, 'Creating' if sync_config['instance_destroy'] else 'Starting', sync_config['service']))

                # startup instance
                resp, instance_id = syncer.startup(service=sync_config['service'], name=sync_name)
                if not resp:
                    # send notification of failure to startup instance
                    notify.send(message='Syncer: %s failed to startup a %s instance. '
                                        'Manually check no instances are still running!' %
                                        (sync_name, 'new' if sync_config['instance_destroy'] else 'existing'))
                    continue

                # setup instance
                resp = syncer.setup(service=sync_config['service'], instance_id=instance_id,
                                    rclone_config=conf.configs['core']['rclone_config_path'])
                if not resp:
                    # send notification of failure to setup instance
                    notify.send(
                        message='Syncer: %s failed to setup a %s instance. '
                                'Manually check no instances are still running!' % (
                                    sync_name, 'new' if sync_config['instance_destroy'] else 'existing'))
                    continue

                # send notification of sync start
                notify.send(message='Sync has begun for syncer: %s' % sync_name)

                # do sync
                resp, resp_delay, resp_trigger = syncer.sync(service=sync_config['service'], instance_id=instance_id,
                                                             dry_run=conf.configs['core']['dry_run'],
                                                             rclone_config=conf.configs['core']['rclone_config_path'])

                if not resp and not resp_delay:
                    log.error("Sync unexpectedly failed for syncer: %s", sync_name)
                    # send unexpected sync fail notification
                    notify.send(
                        message='Sync failed unexpectedly for syncer: %s. '
                                'Manually check no instances are still running!' % sync_name)

                elif not resp and resp_delay and resp_trigger:
                    # non 0 resp_delay result indicates a trigger was met, the result is how many hours to sleep
                    # this syncer for
                    log.info(
                        "Sync aborted due to trigger: %r being met, %s will continue automatic syncing normally in "
                        "%d hours", resp_trigger, sync_name, resp_delay)
                    # add syncer to syncer_delays (which points to syncer_delay)
                    syncer_delays[sync_name] = time.time() + ((60 * 60) * resp_delay)
                    # send aborted sync notification
                    notify.send(
                        message="Sync was aborted for syncer: %s due to trigger %r. Syncs suspended for %d hours" %
                                (sync_name, resp_trigger, resp_delay))
                else:
                    log.info("Syncing completed successfully for syncer: %s", sync_name)
                    # send successful sync notification
                    notify.send(message="Sync was completed successfully for syncer: %s" % sync_name)

                # destroy instance
                resp = syncer.destroy(service=sync_config['service'], instance_id=instance_id)
                if not resp:
                    # send notification of failure to destroy/stop instance
                    notify.send(
                        message="Syncer: %s failed to %s its instance: %s. "
                                "Manually check no instances are still running!" % (
                                    sync_name, 'destroy' if sync_config['instance_destroy'] else 'stop', instance_id))
                else:
                    # send notification of instance destroyed
                    notify.send(message="Syncer: %s has %s its %s instance" % (
                        sync_name, 'destroyed' if sync_config['instance_destroy'] else 'stopped',
                        sync_config['service']))

        except Exception:
            log.exception("Exception occurred while syncing: ")

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
    log.debug("Scheduled disk check triggered for uploader: %s", uploader_name)
    try:
        rclone_settings = conf.configs['remotes'][uploader_name]

        # check suspended uploaders
        if check_suspended_uploaders(uploader_name):
            return

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


def scheduled_syncer(syncer_delays, syncer_name):
    log.info("Scheduled sync triggered for syncer: %s", syncer_name)
    try:
        # check suspended syncers
        if check_suspended_syncers(syncer_delays, syncer_name):
            return

        # do sync
        do_sync(syncer_name, syncer_delays=syncer_delays)

    except Exception:
        log.exception("Unexpected exception occurred while processing syncer: %s", syncer_name)


############################################################
# MAIN
############################################################

if __name__ == "__main__":
    # show latest version info from git
    version.check_version()

    # init multiprocessing
    manager = Manager()
    uploader_delay = manager.dict()
    syncer_delay = manager.dict()

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
        elif conf.args['cmd'] == 'sync':
            log.info("Starting in sync mode")
            log.warning("Sync currently has a bug while displaying output to the console. "
                        "Tail the logfile to view readable logs!")
            init_syncers()
            do_sync(syncer_delays=syncer_delay)
        elif conf.args['cmd'] == 'run':
            log.info("Started in run mode")

            # add uploaders to schedule
            for uploader, uploader_conf in conf.configs['uploader'].items():
                schedule.every(uploader_conf['check_interval']).minutes.do(scheduled_uploader, uploader, uploader_conf)
                log.info("Added %s uploader to schedule, checking available disk space every %d minutes", uploader,
                         uploader_conf['check_interval'])

            # add syncers to schedule
            init_syncers()
            for syncer_name, syncer_conf in conf.configs['syncer'].items():
                schedule.every(syncer_conf['sync_interval']).hours.do(run_process, scheduled_syncer, syncer_delay,
                                                                      syncer_name=syncer_name)
                log.info("Added %s syncer to schedule, syncing every %d hours", syncer_name,
                         syncer_conf['sync_interval'])

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
