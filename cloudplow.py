#!/usr/bin/env python3
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from multiprocessing import Process

import requests
import schedule
from requests.packages.urllib3.exceptions import InsecureRequestWarning

from utils import config, lock, path, decorators, version, misc
from utils.cache import Cache
from utils.notifications import Notifications
from utils.nzbget import Nzbget
from utils.plex import Plex
from utils.rclone import RcloneThrottler, RcloneMover
from utils.syncer import Syncer
from utils.threads import Thread
from utils.unionfs import UnionfsHiddenFolder
from utils.uploader import Uploader

############################################################
# INIT
############################################################

# Logging
log_formatter = logging.Formatter(
    u'%(asctime)s - %(levelname)-10s - %(name)-20s - %(funcName)-30s - %(message)s')
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Set schedule logger to ERROR
logging.getLogger('schedule').setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("sqlitedict").setLevel(logging.WARNING)
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

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
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

# Set chosen logging level
root_logger.setLevel(conf.settings['loglevel'])
log = root_logger.getChild('cloudplow')

# Load config from disk
conf.load()

# Init Cache class
cache = Cache(conf.settings['cachefile'])

# Init Notifications class
notify = Notifications()

# Init Syncer class
syncer = Syncer(conf.configs)

# Ensure lock folder exists
lock.ensure_lock_folder()

# Init thread class
thread = Thread()

# Logic vars
uploader_delay = cache.get_cache('uploader_bans')
syncer_delay = cache.get_cache('syncer_bans')
plex_monitor_thread = None
sa_delay = cache.get_cache('sa_bans')


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


def init_service_accounts():
    global sa_delay
    global uploader_delay

    for uploader_remote, uploader_config in conf.configs['uploader'].items():
        if uploader_remote not in sa_delay:
            sa_delay[uploader_remote] = None
        if 'service_account_path' in uploader_config and os.path.exists(uploader_config['service_account_path']):
            # If service_account path provided, loop over the service account files and provide
            # one at a time when starting the uploader. If upload completes successfully, do not attempt
            # to use the other accounts
            accounts = {os.path.join(os.path.normpath(uploader_config['service_account_path']), file): None for file
                        in os.listdir(os.path.normpath(uploader_config['service_account_path'])) if
                        file.endswith(".json")}
            current_accounts = sa_delay[uploader_remote]
            if current_accounts is not None:
                for account in accounts:
                    if account not in current_accounts:
                        log.debug("New service account %s has been added for remote %s", account, uploader_remote)
                        current_accounts[account] = None
                sa_delay[uploader_remote] = current_accounts
                if len(current_accounts) < len(accounts):
                    log.debug("Additional service accounts were added. Lifting any current bans for remote: %s",
                              uploader_remote)
                    uploader_delay.pop(uploader_remote, None)
            else:
                log.debug("The following accounts are defined: %s and are about to be added to remote %s",
                          str(accounts),
                          uploader_remote)
                sa_delay[uploader_remote] = accounts


def init_syncers():
    try:
        for syncer_name, syncer_config in conf.configs['syncer'].items():
            # remove irrelevant parameters before loading syncer agent
            filtered_config = syncer_config.copy()
            filtered_config.pop('sync_interval', None)
            filtered_config['syncer_name'] = syncer_name
            # load syncer agent
            syncer.load(**filtered_config)
    except Exception:
        log.exception("Exception initializing syncer agents: ")


def check_suspended_sa(uploader_to_check):
    global sa_delay
    try:
        if sa_delay[uploader_to_check] is not None:
            log.debug("Proceeding to check any timeouts which have passed for remote %s", uploader_to_check)
            for account, suspension_expiry in sa_delay[uploader_to_check].items():
                if suspension_expiry is not None:
                    log.debug("Service account %s was previously banned. Checking if timeout has passed",
                              suspension_expiry)
                    # Remove any ban times for service accounts which have passed
                    if time.time() > suspension_expiry:
                        log.debug("Setting ban status for service_account %s to None since timeout has passed", account)
                        current_data = sa_delay[uploader_to_check]
                        current_data[account] = None
                        sa_delay[uploader_to_check] = current_data
    except Exception:
        log.exception("Exception checking suspended service accounts: ")


def check_suspended_uploaders(uploader_to_check=None):
    global uploader_delay

    suspended = False
    try:
        for uploader_name, suspension_expiry in dict(uploader_delay.items()).items():
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


def check_suspended_syncers(syncer_to_check=None):
    global syncer_delay

    suspended = False
    try:
        for syncer_name, suspension_expiry in dict(syncer_delay.items()).items():
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
                syncer_delay.pop(syncer_name, None)
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
    global plex_monitor_thread, uploader_delay
    global sa_delay

    nzbget = None
    nzbget_paused = False

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

                # start the plex stream monitor before the upload begins, if enabled
                if conf.configs['plex']['enabled'] and plex_monitor_thread is None:
                    plex_monitor_thread = thread.start(do_plex_monitor, 'plex-monitor')

                # pause the nzbget queue before starting the upload, if enabled
                if conf.configs['nzbget']['enabled']:
                    nzbget = Nzbget(conf.configs['nzbget']['url'])
                    if nzbget.pause_queue():
                        nzbget_paused = True
                        log.info("Paused the Nzbget download queue, upload commencing!")
                    else:
                        log.error("Failed to pause the Nzbget download queue, upload commencing anyway...")

                uploader = Uploader(uploader_remote, uploader_config, rclone_config,
                                    conf.configs['core']['dry_run'],
                                    conf.configs['core']['rclone_binary_path'],
                                    conf.configs['core']['rclone_config_path'], conf.configs['plex']['enabled'])

                if sa_delay[uploader_remote] is not None:
                    available_accounts = [account for account, last_ban_time in sa_delay[uploader_remote].items() if
                                          last_ban_time is None]
                    available_accounts_size = len(available_accounts)

                    if available_accounts_size:
                        available_accounts = misc.sorted_list_by_digit_asc(available_accounts)

                    log.info("There is %d available service accounts", available_accounts_size)
                    log.debug("Available service accounts: %s", str(available_accounts))

                    # If there are no service accounts available, do not even bother attempting the upload
                    if not available_accounts_size:
                        log.info("Upload aborted due to the fact that no service accounts "
                                 "are currently unbanned and available to use for remote %s",
                                 uploader_remote)
                        # add remote to uploader_delay
                        time_till_unban = misc.get_lowest_remaining_time(sa_delay[uploader_remote])
                        log.info("Lowest Remaining time till unban is %d", time_till_unban)
                        uploader_delay[uploader_remote] = time_till_unban
                    else:
                        for i in range(0, available_accounts_size):
                            uploader.set_service_account(available_accounts[i])
                            resp, resp_trigger = uploader.upload()
                            if resp:
                                current_data = sa_delay[uploader_remote]
                                current_data[available_accounts[i]] = time.time() + ((60 * 60) * resp)
                                sa_delay[uploader_remote] = current_data
                                log.debug("Setting account %s as unbanned at %f", available_accounts[i],
                                          sa_delay[uploader_remote][available_accounts[i]])
                                if i != (len(available_accounts) - 1):
                                    log.info("Upload aborted due to trigger: %r being met, "
                                             "%s is cycling to service_account file: %r",
                                             resp_trigger, uploader_remote, available_accounts[i + 1])
                                    # Set unban time for current service account
                                    log.debug("Setting service account %s as banned for remote: %s",
                                              available_accounts[i], uploader_remote)
                                    continue
                                else:
                                    # non 0 result indicates a trigger was met, the result is how many hours
                                    # to sleep this remote for
                                    # Before banning remote, check that a service account did not become unbanned
                                    # during upload
                                    check_suspended_sa(sa_delay[uploader_remote])

                                    unbanTime = misc.get_lowest_remaining_time(sa_delay[uploader_remote])
                                    if unbanTime is not None:
                                        log.info(
                                            "Upload aborted due to trigger: %r being met, %s will continue automatic "
                                            "uploading normally in %d hours", resp_trigger, uploader_remote, resp)

                                        # add remote to uploader_delay
                                        log.debug("Adding unban time for %s as %f", uploader_remote,
                                                  misc.get_lowest_remaining_time(sa_delay[uploader_remote]))
                                        uploader_delay[uploader_remote] = misc.get_lowest_remaining_time(
                                            sa_delay[uploader_remote])

                                        # send aborted upload notification
                                        notify.send(
                                            message="Upload was aborted for remote: %s due to trigger %r. "
                                                    "Uploads suspended for %d hours" %
                                                    (uploader_remote, resp_trigger, resp))
                            else:
                                # send successful upload notification
                                notify.send(
                                    message="Upload was completed successfully for remote: %s" % uploader_remote)

                                # Remove ban for service account
                                sa_delay[uploader_remote][available_accounts[i]] = None
                                break
                else:
                    resp, resp_trigger = uploader.upload()
                    if resp:
                        if uploader_remote not in uploader_delay:
                            # this uploader was not already in the delay dict, so lets put it there
                            log.info(
                                "Upload aborted due to trigger: %r being met, %s will continue automatic uploading "
                                "normally in %d hours", resp_trigger, uploader_remote, resp)
                            # add remote to uploader_delay
                            uploader_delay[uploader_remote] = time.time() + ((60 * 60) * resp)
                            # send aborted upload notification
                            notify.send(
                                message="Upload was aborted for remote: %s due to trigger %r. Uploads suspended for %d"
                                        " hours" % (uploader_remote, resp_trigger, resp))
                        else:
                            # this uploader is already in the delay dict, lets not delay it any further
                            log.info(
                                "Upload aborted due to trigger: %r being met for %s uploader",
                                resp_trigger, uploader_remote)
                            # send aborted upload notification
                            notify.send(
                                message="Upload was aborted for remote: %s due to trigger %r." %
                                        (uploader_remote, resp_trigger))
                    else:
                        log.info("Upload completed successfully for uploader: %s", uploader_remote)
                        # send successful upload notification
                        notify.send(message="Upload was completed successfully for remote: %s" % uploader_remote)
                        # remove uploader from uploader_delays (as its no longer banned)
                        if uploader_remote in uploader_delay and uploader_delay.pop(uploader_remote, None) is not None:
                            # this uploader was in the delay dict, but upload was successful, lets remove it
                            log.info("%s is no longer suspended due to a previous aborted upload!", uploader_remote)

                # remove leftover empty directories from disk
                if not conf.configs['core']['dry_run']:
                    uploader.remove_empty_dirs()

                # resume the nzbget queue, if enabled
                if conf.configs['nzbget']['enabled'] and nzbget is not None and nzbget_paused:
                    if nzbget.resume_queue():
                        nzbget_paused = False
                        log.info("Resumed the Nzbget download queue!")
                    else:
                        log.error("Failed to resume the Nzbget download queue??")

                # move from staging remote to main ?
                if 'mover' in uploader_config and 'enabled' in uploader_config['mover']:
                    if not uploader_config['mover']['enabled']:
                        # if not enabled, continue the uploader loop
                        continue

                    # validate we have the bare minimum config settings set
                    required_configs = ['move_from_remote', 'move_to_remote', 'rclone_extras']
                    required_set = True
                    for setting in required_configs:
                        if setting not in uploader_config['mover']:
                            log.error("Unable to act on '%s' mover because there was no '%s' setting in the mover "
                                      "configuration", uploader_remote, setting)
                            required_set = False
                            break

                    # do move if good
                    if required_set:
                        mover = RcloneMover(uploader_config['mover'], conf.configs['core']['rclone_binary_path'],
                                            conf.configs['core']['rclone_config_path'],
                                            conf.configs['core']['dry_run'], conf.configs['plex']['enabled'])
                        log.info("Move starting from %r -> %r",
                                 uploader_config['mover']['move_from_remote'],
                                 uploader_config['mover']['move_to_remote'])

                        # send notification that mover has started
                        notify.send(
                            message="Move has started for %s -> %s" % (uploader_config['mover']['move_from_remote'],
                                                                       uploader_config['mover']['move_to_remote']))

                        if mover.move():
                            log.info("Move completed successfully from %r -> %r",
                                     uploader_config['mover']['move_from_remote'],
                                     uploader_config['mover']['move_to_remote'])
                            # send notification move has finished
                            notify.send(
                                message="Move finished successfully for %s -> %s" % (
                                    uploader_config['mover']['move_from_remote'],
                                    uploader_config['mover']['move_to_remote']))
                        else:
                            log.error("Move failed from %r -> %r ....?", uploader_config['mover']['move_from_remote'],
                                      uploader_config['mover']['move_to_remote'])
                            # send notification move has failed
                            notify.send(
                                message="Move failed for %s -> %s" % (
                                    uploader_config['mover']['move_from_remote'],
                                    uploader_config['mover']['move_to_remote']))

        except Exception:
            log.exception("Exception occurred while uploading: ")

    log.info("Finished upload")


@decorators.timed
def do_sync(use_syncer=None):
    global syncer_delay

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
                if not sync_config['service'].lower() == 'local':
                    notify.send(message='Sync initiated for syncer: %s. %s %s instance...' % (
                        sync_name, 'Creating' if sync_config['instance_destroy'] else 'Starting',
                        sync_config['service']))

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
                    if sync_name not in syncer_delay:
                        # this syncer was not in the syncer delay dict, so lets put it there
                        log.info(
                            "Sync aborted due to trigger: %r being met, %s will continue automatic syncing normally in "
                            "%d hours", resp_trigger, sync_name, resp_delay)
                        # add syncer to syncer_delay
                        syncer_delay[sync_name] = time.time() + ((60 * 60) * resp_delay)
                        # send aborted sync notification
                        notify.send(
                            message="Sync was aborted for syncer: %s due to trigger %r. Syncs suspended for %d hours" %
                                    (sync_name, resp_trigger, resp_delay))
                    else:
                        # this syncer was already in the syncer delay dict, so lets not delay it any further
                        log.info(
                            "Sync aborted due to trigger: %r being met for %s syncer", resp_trigger, sync_name)
                        # send aborted sync notification
                        notify.send(
                            message="Sync was aborted for syncer: %s due to trigger %r." %
                                    (sync_name, resp_trigger))
                else:
                    log.info("Syncing completed successfully for syncer: %s", sync_name)
                    # send successful sync notification
                    notify.send(message="Sync was completed successfully for syncer: %s" % sync_name)
                    # remove syncer from syncer_delay(as its no longer banned)
                    if sync_name in syncer_delay and syncer_delay.pop(sync_name, None) is not None:
                        # this syncer was in the delay dict, but sync was successful, lets remove it
                        log.info("%s is no longer suspended due to a previous aborted sync!", sync_name)

                # destroy instance
                resp = syncer.destroy(service=sync_config['service'], instance_id=instance_id)
                if not resp and not sync_config['service'].lower() == 'local':
                    # send notification of failure to destroy/stop instance
                    notify.send(
                        message="Syncer: %s failed to %s its instance: %s. "
                                "Manually check no instances are still running!" % (
                                    sync_name, 'destroy' if sync_config['instance_destroy'] else 'stop', instance_id))
                else:
                    # send notification of instance destroyed
                    if not sync_config['service'].lower() == 'local':
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
                hidden = UnionfsHiddenFolder(hidden_folder, conf.configs['core']['dry_run'],
                                             conf.configs['core']['rclone_binary_path'],
                                             conf.configs['core']['rclone_config_path'])

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


@decorators.timed
def do_plex_monitor():
    global plex_monitor_thread

    # create the plex object
    plex = Plex(conf.configs['plex']['url'], conf.configs['plex']['token'])
    if not plex.validate():
        log.error(
            "Aborting Plex Media Server stream monitor due to failure to validate supplied server URL and/or Token.")
        plex_monitor_thread = None
        return

    # sleep 15 seconds to allow rclone to start
    log.info("Plex Media Server URL + Token were validated. Sleeping for 15 seconds before checking Rclone RC URL.")
    time.sleep(15)

    # create the rclone throttle object
    rclone = RcloneThrottler(conf.configs['plex']['rclone']['url'])
    if not rclone.validate():
        log.error("Aborting Plex Media Server stream monitor due to failure to validate supplied Rclone RC URL.")
        plex_monitor_thread = None
        return
    else:
        log.info("Rclone RC URL was validated. Stream monitoring for Plex Media Server will now begin.")

    throttled = False
    throttle_speed = None
    lock_file = lock.upload()
    while lock_file.is_locked():
        streams = plex.get_streams()
        if streams is None:
            log.error("Failed to check Plex Media Server stream(s). Trying again in %d seconds...",
                      conf.configs['plex']['poll_interval'])
        else:
            # we had a response
            stream_count = 0
            for stream in streams:
                if stream.state == 'playing' or stream.state == 'buffering':
                    stream_count += 1

            # are we already throttled?
            if ((not throttled or (throttled and not rclone.throttle_active(throttle_speed))) and (
                    stream_count >= conf.configs['plex']['max_streams_before_throttle'])):
                log.info("There was %d playing stream(s) on Plex Media Server while it was currently un-throttled.",
                         stream_count)
                for stream in streams:
                    log.info(stream)
                log.info("Upload throttling will now commence.")

                # send throttle request
                throttle_speed = misc.get_nearest_less_element(conf.configs['plex']['rclone']['throttle_speeds'],
                                                               stream_count)
                throttled = rclone.throttle(throttle_speed)

                # send notification
                if throttled and conf.configs['plex']['notifications']:
                    notify.send(
                        message="Throttled current upload to %s because there was %d playing stream(s) on Plex" %
                                (throttle_speed, stream_count))

            elif throttled:
                if stream_count < conf.configs['plex']['max_streams_before_throttle']:
                    log.info(
                        "There was less than %d playing stream(s) on Plex Media Server while it was currently throttled. "
                        "Removing throttle ...", conf.configs['plex']['max_streams_before_throttle'])
                    # send un-throttle request
                    throttled = not rclone.no_throttle()
                    throttle_speed = None

                    # send notification
                    if not throttled and conf.configs['plex']['notifications']:
                        notify.send(
                            message="Un-throttled current upload because there was less than %d playing stream(s) on "
                                    "Plex Media Server" % conf.configs['plex']['max_streams_before_throttle'])

                elif misc.get_nearest_less_element(conf.configs['plex']['rclone']['throttle_speeds'],
                                                   stream_count) != throttle_speed:
                    # throttle speed changed, probably due to more/less streams, re-throttle
                    throttle_speed = misc.get_nearest_less_element(conf.configs['plex']['rclone']['throttle_speeds'],
                                                                   stream_count)
                    log.info("Adjusting throttle speed for current upload to %s because there "
                             "was now %d playing stream(s) on Plex Media Server", throttle_speed, stream_count)

                    throttled = rclone.throttle(throttle_speed)

                    # send notification
                    if throttled and conf.configs['plex']['notifications']:
                        notify.send(
                            message='Throttle for current upload was adjusted to %s due to %d playing stream(s)'
                                    ' on Plex Media Server' % (throttle_speed, stream_count))

                else:
                    log.info(
                        "There was %d playing stream(s) on Plex Media Server it was already throttled to %s. Throttling "
                        "will continue.", stream_count, throttle_speed)

        # the lock_file exists, so we can assume an upload is in progress at this point
        time.sleep(conf.configs['plex']['poll_interval'])

    log.info("Finished monitoring Plex stream(s)!")
    plex_monitor_thread = None


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

        # clear any banned service accounts
        check_suspended_sa(uploader_name)

        # check used disk space
        used_space = path.get_size(rclone_settings['upload_folder'], uploader_settings['size_excludes'])

        # if disk space is above the limit, clean hidden files then upload
        if used_space >= uploader_settings['max_size_gb']:
            log.info("Uploader: %s. Local folder size is currently %d GB over the maximum limit of %d GB",
                     uploader_name, used_space - uploader_settings['max_size_gb'], uploader_settings['max_size_gb'])

            # does this uploader have schedule settings
            if 'schedule' in uploader_settings and uploader_settings['schedule']['enabled']:
                # there is a schedule set for this uploader, check if we are within the allowed times
                current_time = time.strftime('%H:%M')
                if not misc.is_time_between((uploader_settings['schedule']['allowed_from'],
                                             uploader_settings['schedule']['allowed_until'])):
                    log.info(
                        "Uploader: %s. The current time %s is not within the allowed upload time periods %s -> %s",
                        uploader_name, current_time, uploader_settings['schedule']['allowed_from'],
                        uploader_settings['schedule']['allowed_until'])
                    return

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


def scheduled_syncer(syncer_name):
    log.info("Scheduled sync triggered for syncer: %s", syncer_name)
    try:
        # check suspended syncers
        if check_suspended_syncers(syncer_name):
            return

        # do sync
        do_sync(syncer_name)

    except Exception:
        log.exception("Unexpected exception occurred while processing syncer: %s", syncer_name)


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
            # initialize service accounts if provided in confing
            init_service_accounts()
            do_hidden()
            do_upload()
        elif conf.args['cmd'] == 'sync':
            log.info("Starting in sync mode")
            log.warning("Sync currently has a bug while displaying output to the console. "
                        "Tail the logfile to view readable logs!")
            init_syncers()
            do_sync()
        elif conf.args['cmd'] == 'run':
            log.info("Started in run mode")

            # initialize service accounts if provided in confing
            init_service_accounts()

            # add uploaders to schedule
            for uploader, uploader_conf in conf.configs['uploader'].items():
                schedule.every(uploader_conf['check_interval']).minutes.do(scheduled_uploader, uploader, uploader_conf)
                log.info("Added %s uploader to schedule, checking available disk space every %d minutes", uploader,
                         uploader_conf['check_interval'])

            # add syncers to schedule
            init_syncers()
            for syncer_name, syncer_conf in conf.configs['syncer'].items():
                if syncer_conf['service'].lower() == 'local':
                    schedule.every(syncer_conf['sync_interval']).hours.do(scheduled_syncer, syncer_name=syncer_name)
                else:
                    schedule.every(syncer_conf['sync_interval']).hours.do(run_process, scheduled_syncer,
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
