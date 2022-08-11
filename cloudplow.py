#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from multiprocessing import Process

import schedule

from utils import config, lock, path, decorators, version, misc
from utils.cache import Cache
from utils.notifications import Notifications
from utils.nzbget import Nzbget
from utils.sabnzbd import Sabnzbd
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
log_formatter = logging.Formatter(u'%(asctime)s - %(levelname)-10s - %(name)-20s - %(funcName)-30s - %(message)s')
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Set schedule logger to ERROR
logging.getLogger('schedule').setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("sqlitedict").setLevel(logging.WARNING)

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
    log.debug("Start initializing of service accounts.")
    for uploader_remote, uploader_config in conf.configs['uploader'].items():
        if uploader_remote not in sa_delay:
            sa_delay[uploader_remote] = None
        if 'service_account_path' in uploader_config and os.path.exists(uploader_config['service_account_path']):
            # If service_account path provided, loop over the service account files and provide
            # one at a time when starting the uploader. If upload completes successfully, do not attempt
            # to use the other accounts
            accounts = {os.path.join(os.path.normpath(uploader_config['service_account_path']),
                                     sa_file): None for sa_file in
                        os.listdir(os.path.normpath(uploader_config['service_account_path'])) if
                        sa_file.endswith(".json")}
            current_accounts = sa_delay[uploader_remote]
            if current_accounts is not None:
                # Service account files may have moved, invalidate any missing cached accounts.
                cached_accounts = list(current_accounts)
                for cached_account in cached_accounts:
                    log.debug(f"Checking for cached service account file '{cached_account}' for remote '{uploader_remote}'")
                    if not cached_account.startswith(os.path.normpath(uploader_config['service_account_path'])):
                        log.debug(f"Cached service account file '{cached_account}' for remote '{uploader_remote}' is not located in specified service_account_path ('{uploader_config['service_account_path']}'). Removing from available accounts.")
                        current_accounts.pop(cached_account)
                    if not os.path.exists(cached_account):
                        log.debug(f"Cached service account file '{cached_account}' for remote '{uploader_remote}' could not be located. Removing from available accounts.")
                        current_accounts.pop(cached_account)

                # Add any new account files.
                for account in accounts:
                    if account not in current_accounts:
                        log.debug(f"New service account '{account}' has been added for remote '{uploader_remote}'")
                        current_accounts[account] = None
                sa_delay[uploader_remote] = current_accounts
                if len(current_accounts) < len(accounts):
                    log.debug(f"Additional service accounts were added. Lifting any current bans for remote '{uploader_remote}'")
                    uploader_delay.pop(uploader_remote, None)
            else:
                log.debug(f"The following accounts are defined: '{accounts}' and are about to be added to remote '{uploader_remote}'")
                sa_delay[uploader_remote] = accounts
    log.debug("Finished initializing of service accounts.")


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
            log.debug(f"Proceeding to check any timeouts which have passed for remote {uploader_to_check}")
            for account, suspension_expiry in sa_delay[uploader_to_check].items():
                if suspension_expiry is not None:
                    log.debug(f"Service account {suspension_expiry} was previously banned. Checking if timeout has passed")
                    # Remove any ban times for service accounts which have passed
                    if time.time() > suspension_expiry:
                        log.debug(f"Setting ban status for service_account {account} to None since timeout has passed")
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
                use_logger = (
                    log.debug
                    if not uploader_to_check or uploader_name != uploader_to_check
                    else log.info
                )

                use_logger(f"{uploader_name} is still suspended due to a previously aborted upload. Normal operation in {misc.seconds_to_string(int(suspension_expiry - time.time()))} at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(suspension_expiry))}")
                # return True when suspended if uploader_to_check is supplied and this is that remote
                if uploader_to_check and uploader_name == uploader_to_check:
                    suspended = True
            else:
                log.warning(f"{uploader_name} is no longer suspended due to a previous aborted upload!")
                uploader_delay.pop(uploader_name, None)
                # send notification that remote is no longer timed out
                notify.send(message=f"Upload suspension has expired for remote: {uploader_name}")

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
                use_logger = (
                    log.debug
                    if not syncer_to_check or syncer_name != syncer_to_check
                    else log.info
                )

                use_logger(f"{syncer_name} is still suspended due to a previously aborted sync. Normal operation in {misc.seconds_to_string(int(suspension_expiry - time.time()))} at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(suspension_expiry))}")
                # return True when suspended if syncer_to_check is supplied and this is that remote
                if syncer_to_check and syncer_name == syncer_to_check:
                    suspended = True
            else:
                log.warning(f"{syncer_name} is no longer suspended due to a previous aborted sync!")
                syncer_delay.pop(syncer_name, None)
                # send notification that remote is no longer timed out
                notify.send(message=f"Sync suspension has expired for syncer: {syncer_name}")

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

    sabnzbd = None
    sabnzbd_paused = False

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
                notify.send(message=f"Upload of {path.get_size(rclone_config['upload_folder'], uploader_config['size_excludes'])} GB has begun for remote: {uploader_remote}")

                # start the plex stream monitor before the upload begins, if enabled for both plex and the uploader
                if conf.configs['plex']['enabled'] and plex_monitor_thread is None:
                    # Only disable throttling if 'can_be_throttled' is both present in uploader_config and is set to False.
                    if 'can_be_throttled' in uploader_config and not uploader_config['can_be_throttled']:
                        log.debug(f"Skipping check for Plex stream due to throttling disabled in remote: {uploader_remote}")
                    # Otherwise, assume throttling is desired.
                    else:
                        plex_monitor_thread = thread.start(do_plex_monitor, 'plex-monitor')

                # pause the nzbget queue before starting the upload, if enabled
                if conf.configs['nzbget']['enabled']:
                    nzbget = Nzbget(conf.configs['nzbget']['url'])
                    if nzbget.pause_queue():
                        nzbget_paused = True
                        log.info("Paused the Nzbget download queue, upload commencing!")
                    else:
                        log.error("Failed to pause the Nzbget download queue, upload commencing anyway...")

                # pause the sabnzbd queue before starting the upload, if enabled
                if conf.configs['sabnzbd']['enabled']:
                    sabnzbd = Sabnzbd(conf.configs['sabnzbd']['url'], conf.configs['sabnzbd']['apikey'])
                    if sabnzbd.pause_queue():
                        sabnzbd_paused = True
                        log.info("Paused the Sabnzbd download queue, upload commencing!")
                    else:
                        print(sabnzbd.pause_queue())
                        log.error("Failed to pause the Sabnzbd download queue, upload commencing anyway...")

                uploader = Uploader(uploader_remote,
                                    uploader_config,
                                    rclone_config,
                                    conf.configs['core']['rclone_binary_path'],
                                    conf.configs['core']['rclone_config_path'],
                                    conf.configs['plex'],
                                    conf.configs['core']['dry_run'])

                if sa_delay[uploader_remote] is not None:
                    available_accounts = [account for account, last_ban_time in sa_delay[uploader_remote].items() if
                                          last_ban_time is None]
                    available_accounts_size = len(available_accounts)

                    if available_accounts_size:
                        available_accounts = misc.sorted_list_by_digit_asc(available_accounts)

                    log.info(f"There is {available_accounts_size} available service accounts")
                    log.debug(f"Available service accounts: {str(available_accounts)}")

                    # If there are no service accounts available, do not even bother attempting the upload
                    if not available_accounts_size:
                        log.info(f"Upload aborted due to the fact that no service accounts are currently unbanned and available to use for remote {uploader_remote}")
                        # add remote to uploader_delay
                        time_till_unban = misc.get_lowest_remaining_time(sa_delay[uploader_remote])
                        log.info(f"Lowest Remaining time till unban is {time_till_unban}")
                        uploader_delay[uploader_remote] = time_till_unban
                    else:
                        for i in range(available_accounts_size):
                            uploader.set_service_account(available_accounts[i])
                            resp_delay, resp_trigger = uploader.upload()
                            if resp_delay:
                                current_data = sa_delay[uploader_remote]
                                current_data[available_accounts[i]] = time.time() + ((60 * 60) * resp_delay)
                                sa_delay[uploader_remote] = current_data
                                log.debug(f"Setting account {available_accounts[i]} as unbanned at {sa_delay[uploader_remote][available_accounts[i]]}")
                                if i != (len(available_accounts) - 1):
                                    log.info(f"Upload aborted due to trigger: {resp_trigger} being met, {uploader_remote} is cycling to service_account file: {available_accounts[i + 1]}")
                                    # Set unban time for current service account
                                    log.debug(f"Setting service account {available_accounts[i]} as banned for remote: {uploader_remote}")
                                    continue
                                else:
                                    # non 0 result indicates a trigger was met, the result is how many hours
                                    # to sleep this remote for
                                    # Before banning remote, check that a service account did not become unbanned
                                    # during upload
                                    check_suspended_sa(sa_delay[uploader_remote])

                                    unban_time = misc.get_lowest_remaining_time(sa_delay[uploader_remote])
                                    if unban_time is not None:
                                        log.info(f"Upload aborted due to trigger: {resp_trigger} being met, {uploader_remote} will continue automatic uploading normally in {resp_delay} hours")

                                        # add remote to uploader_delay
                                        log.debug(f"Adding unban time for {uploader_remote} as {misc.get_lowest_remaining_time(sa_delay[uploader_remote])}")
                                        uploader_delay[uploader_remote] = misc.get_lowest_remaining_time(
                                            sa_delay[uploader_remote])

                                        # send aborted upload notification
                                        notify.send(message=f"Upload was aborted for remote: {uploader_remote} due to trigger {resp_trigger}. Uploads suspended for {resp_delay} hours")
                            else:
                                # send successful upload notification
                                notify.send(message=f"Upload was completed successfully for remote: {uploader_remote}")

                                # Remove ban for service account
                                sa_delay[uploader_remote][available_accounts[i]] = None
                                break
                else:
                    resp_delay, resp_trigger = uploader.upload()
                    if resp_delay:
                        if uploader_remote not in uploader_delay:
                            # this uploader was not already in the delay dict, so lets put it there
                            log.info(f"Upload aborted due to trigger: {resp_trigger} being met, {uploader_remote} will continue automatic uploading normally in {resp_delay} hours")
                            # add remote to uploader_delay
                            uploader_delay[uploader_remote] = time.time() + 60 ** 2 * resp_delay
                            # send aborted upload notification
                            notify.send(message=f"Upload was aborted for remote: {uploader_remote} due to trigger {resp_trigger}. Uploads suspended for {resp_delay} hours")
                        else:
                            # this uploader is already in the delay dict, lets not delay it any further
                            log.info(f"Upload aborted due to trigger: {resp_trigger} being met for {uploader_remote} uploader")
                            # send aborted upload notification
                            notify.send(message=f"Upload was aborted for remote: {uploader_remote} due to trigger {resp_trigger}.")
                    else:
                        log.info(f"Upload completed successfully for uploader: {uploader_remote}")
                        # send successful upload notification
                        notify.send(message=f"Upload was completed successfully for remote: {uploader_remote}")

                        # remove uploader from uploader_delays (as its no longer banned)
                        if uploader_remote in uploader_delay and uploader_delay.pop(uploader_remote, None) is not None:
                            # this uploader was in the delay dict, but upload was successful, lets remove it
                            log.info(f"{uploader_remote} is no longer suspended due to a previous aborted upload!")

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
                # resume the Sabnzbd queue, if enabled
                if conf.configs['sabnzbd']['enabled'] and sabnzbd is not None and sabnzbd_paused:
                    if sabnzbd.resume_queue():
                        sabnzbd_paused = False
                        log.info("Resumed the Sabnzbd download queue!")
                    else:
                        log.error("Failed to resume the Sabnzbd download queue??")

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
                            log.error(f"Unable to act on '{uploader_remote}' mover because there was no '{setting}' setting in the mover configuration")
                            required_set = False
                            break

                    # do move if good
                    if required_set:
                        mover = RcloneMover(uploader_config['mover'],
                                            conf.configs['core']['rclone_binary_path'],
                                            conf.configs['core']['rclone_config_path'],
                                            conf.configs['plex'],
                                            conf.configs['core']['dry_run'])
                        log.info(f"Move starting from {uploader_config['mover']['move_from_remote']} -> {uploader_config['mover']['move_to_remote']}")

                        # send notification that mover has started
                        notify.send(message=f"Move has started for {uploader_config['mover']['move_from_remote']} -> {uploader_config['mover']['move_to_remote']}")

                        if mover.move():
                            log.info(f"Move completed successfully from {uploader_config['mover']['move_from_remote']} -> {uploader_config['mover']['move_to_remote']}")
                            # send notification move has finished
                            notify.send(message=f"Move finished successfully for {uploader_config['mover']['move_from_remote']} -> {uploader_config['mover']['move_to_remote']}")

                        else:
                            log.error(f"Move failed from {uploader_config['mover']['move_from_remote']} -> {uploader_config['mover']['move_to_remote']} ....?")
                            # send notification move has failed
                            notify.send(message=f"Move failed for {uploader_config['mover']['move_from_remote']} -> {uploader_config['mover']['move_to_remote']}")

        except Exception:
            log.exception("Exception occurred while uploading: ")
            notify.send(message="Exception occurred while uploading: ")

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
                if sync_config['service'].lower() != 'local':
                    notify.send(message=f"Sync initiated for syncer: {sync_name}. {'Creating' if sync_config['instance_destroy'] else 'Starting'} {sync_config['service']} instance...")

                # startup instance
                resp, instance_id = syncer.startup(service=sync_config['service'], name=sync_name)
                if not resp:
                    # send notification of failure to startup instance
                    notify.send(message=f'Syncer: {sync_name} failed to startup a {"new" if sync_config["instance_destroy"] else "existing"} instance. Manually check no instances are still running!')
                    continue

                # setup instance
                resp = syncer.setup(service=sync_config['service'], instance_id=instance_id,
                                    rclone_config=conf.configs['core']['rclone_config_path'])
                if not resp:
                    # send notification of failure to set up instance
                    notify.send(message=f'Syncer: {sync_name} failed to setup a {"new" if sync_config["instance_destroy"] else "existing"} instance. Manually check no instances are still running!')
                    continue

                # send notification of sync start
                notify.send(message=f'Sync has begun for syncer: {sync_name}')

                # do sync
                resp, resp_delay, resp_trigger = syncer.sync(service=sync_config['service'], instance_id=instance_id,
                                                             dry_run=conf.configs['core']['dry_run'],
                                                             rclone_config=conf.configs['core']['rclone_config_path'])

                if not resp and not resp_delay:
                    log.error("Sync unexpectedly failed for syncer: %s", sync_name)
                    # send unexpected sync fail notification
                    notify.send(message=f'Sync failed unexpectedly for syncer: {sync_name}. Manually check no instances are still running!')

                elif not resp and resp_trigger:
                    # non 0 resp_delay result indicates a trigger was met, the result is how many hours to sleep
                    if sync_name not in syncer_delay:
                        # this syncer was not in the syncer delay dict, so lets put it there
                        log.info(f"Sync aborted due to trigger: {resp_trigger} being met, {sync_name} will continue automatic syncing normally in {resp_delay} hours")
                        # add syncer to syncer_delay
                        syncer_delay[sync_name] = time.time() + 60 ** 2 * resp_delay
                        # send aborted sync notification
                        notify.send(message=f"Sync was aborted for syncer: {sync_name} due to trigger {resp_trigger}. Syncs suspended for {resp_delay} hours")
                    else:
                        # this syncer was already in the syncer delay dict, so lets not delay it any further
                        log.info(f"Sync aborted due to trigger: {resp_trigger} being met for {sync_name} syncer")
                        # send aborted sync notification
                        notify.send(message=f"Sync was aborted for syncer: {sync_name} due to trigger {resp_trigger}.")
                else:
                    log.info(f"Syncing completed successfully for syncer: {sync_name}")
                    # send successful sync notification
                    notify.send(message=f"Sync was completed successfully for syncer: {sync_name}")
                    # remove syncer from syncer_delay(as its no longer banned)
                    if sync_name in syncer_delay and syncer_delay.pop(sync_name, None) is not None:
                        # this syncer was in the delay dict, but sync was successful, lets remove it
                        log.info(f"{sync_name} is no longer suspended due to a previous aborted sync!")

                # destroy instance
                resp = syncer.destroy(service=sync_config['service'], instance_id=instance_id)
                if not resp and sync_config['service'].lower() != 'local':
                    # send notification of failure to destroy/stop instance
                    notify.send(message=f"Syncer: {sync_name} failed to {'destroy' if sync_config['instance_destroy'] else 'stop'} its instance: {instance_id}. Manually check no instances are still running!")
                elif sync_config['service'].lower() != 'local':
                    notify.send(
                        message=f"Syncer: {sync_name} has {'destroyed' if sync_config['instance_destroy'] else 'stopped'} its {sync_config['service']} instance")

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
                        notify.send(message=f"Cleaned {deleted_ok} hidden(s) with {deleted_fail} failure(s) from remote: {hidden_remote_name}")

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
        log.error("Aborting Plex Media Server stream monitor due to failure to validate supplied server URL and/or Token.")
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
            log.error(f"Failed to check Plex Media Server stream(s). Trying again in {conf.configs['plex']['poll_interval']} seconds...")
        else:
            # we had a response
            stream_count = sum(
                stream.state in ['playing', 'buffering'] and not stream.local
                for stream in streams
            )
            local_stream_count = sum(
                stream.state in ['playing', 'buffering'] and stream.local
                for stream in streams
            )

            # if we are accounting for local streams, add them to the stream count
            if not conf.configs['plex']['ignore_local_streams']:
                stream_count += local_stream_count

            # are we already throttled?
            if ((not throttled or (throttled and not rclone.throttle_active(throttle_speed))) and (
                    stream_count >= conf.configs['plex']['max_streams_before_throttle'])):
                log.info(f"There was {stream_count} playing stream(s) on Plex Media Server while it was currently un-throttled.")
                for stream in streams:
                    log.info(stream)
                log.info("Upload throttling will now commence.")

                # send throttle request
                throttle_speed = misc.get_nearest_less_element(conf.configs['plex']['rclone']['throttle_speeds'],
                                                               stream_count)
                throttled = rclone.throttle(throttle_speed)

                # send notification
                if throttled and conf.configs['plex']['notifications']:
                    notify.send(message=f"Throttled current upload to {throttle_speed} because there was {stream_count} playing stream(s) on Plex")

            elif throttled:
                if stream_count < conf.configs['plex']['max_streams_before_throttle']:
                    log.info(f"There was less than {conf.configs['plex']['max_streams_before_throttle']} playing stream(s) on Plex Media Server while it was currently throttled. Removing throttle ...")
                    # send un-throttle request
                    throttled = not rclone.no_throttle()
                    throttle_speed = None

                    # send notification
                    if not throttled and conf.configs['plex']['notifications']:
                        notify.send(message=f"Un-throttled current upload because there was less than {conf.configs['plex']['max_streams_before_throttle']} playing stream(s) on Plex Media Server")

                elif misc.get_nearest_less_element(conf.configs['plex']['rclone']['throttle_speeds'],
                                                   stream_count) != throttle_speed:
                    # throttle speed changed, probably due to more/fewer streams, re-throttle
                    throttle_speed = misc.get_nearest_less_element(conf.configs['plex']['rclone']['throttle_speeds'],
                                                                   stream_count)
                    log.info(f"Adjusting throttle speed for current upload to {throttle_speed} because there was now {stream_count} playing stream(s) on Plex Media Server")

                    throttled = rclone.throttle(throttle_speed)

                    # send notification
                    if throttled and conf.configs['plex']['notifications']:
                        notify.send(message=f'Throttle for current upload was adjusted to {throttle_speed} due to {stream_count} playing stream(s) on Plex Media Server')

                else:
                    log.info(f"There was {stream_count} playing stream(s) on Plex Media Server it was already throttled to {throttle_speed}. Throttling will continue.")

        # the lock_file exists, so we can assume an upload is in progress at this point
        time.sleep(conf.configs['plex']['poll_interval'])

    log.info("Finished monitoring Plex stream(s)!")
    plex_monitor_thread = None


############################################################
# SCHEDULED FUNCS
############################################################

def scheduled_uploader(uploader_name, uploader_settings):
    log.debug(f"Scheduled disk check triggered for uploader: {uploader_name}")
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
            log.info(f"Uploader: {uploader_name}. Local folder size is currently {used_space - uploader_settings['max_size_gb']} GB over the maximum limit of {uploader_settings['max_size_gb']} GB")

            # does this uploader have schedule settings
            if 'schedule' in uploader_settings and uploader_settings['schedule']['enabled']:
                # there is a schedule set for this uploader, check if we are within the allowed times
                current_time = time.strftime('%H:%M')
                if not misc.is_time_between((uploader_settings['schedule']['allowed_from'],
                                             uploader_settings['schedule']['allowed_until'])):
                    log.info(f"Uploader: {uploader_name}. The current time {current_time} is not within the allowed upload time periods {uploader_settings['schedule']['allowed_from']} -> {uploader_settings['schedule']['allowed_until']}")
                    return

            # clean hidden files
            do_hidden()
            # upload
            do_upload(uploader_name)

        else:
            log.info(f"Uploader: {uploader_name}. Local folder size is currently {used_space} GB. Still have {uploader_settings['max_size_gb'] - used_space} GB remaining before its eligible to begin uploading...")

    except Exception:
        log.exception(f"Unexpected exception occurred while processing uploader {uploader_name}: ")


def scheduled_syncer(syncer_name):
    log.info(f"Scheduled sync triggered for syncer: {syncer_name}")
    try:
        # check suspended syncers
        if check_suspended_syncers(syncer_name):
            return

        # do sync
        do_sync(syncer_name)

    except Exception:
        log.exception(f"Unexpected exception occurred while processing syncer: {syncer_name}")


############################################################
# MAIN
############################################################


if __name__ == "__main__":
    # show the latest version info from git
    version.check_version()

    # run chosen mode
    try:

        if conf.args['cmd'] == 'clean':
            log.info("Started in clean mode")
            # init notifications
            init_notifications()
            do_hidden()
        elif conf.args['cmd'] == 'upload':
            log.info("Started in upload mode")
            # init notifications
            init_notifications()
            # initialize service accounts if provided in config
            init_service_accounts()
            do_hidden()
            do_upload()
        elif conf.args['cmd'] == 'sync':
            log.info("Starting in sync mode")
            log.warning("Sync currently has a bug while displaying output to the console. Tail the logfile to view readable logs!")
            # init notifications
            init_notifications()
            init_syncers()
            do_sync()
        elif conf.args['cmd'] == 'run':
            log.info("Started in run mode")

            # init notifications
            init_notifications()
            # initialize service accounts if provided in confing
            init_service_accounts()

            # add uploaders to schedule
            for uploader, uploader_conf in conf.configs['uploader'].items():
                schedule.every(uploader_conf['check_interval']).minutes.do(scheduled_uploader, uploader, uploader_conf)
                log.info(f"Added {uploader} uploader to schedule, checking available disk space every {uploader_conf['check_interval']} minutes")

            # add syncers to schedule
            init_syncers()
            for syncer_name, syncer_conf in conf.configs['syncer'].items():
                if syncer_conf['service'].lower() == 'local':
                    schedule.every(syncer_conf['sync_interval']).hours.do(scheduled_syncer, syncer_name=syncer_name)
                else:
                    schedule.every(syncer_conf['sync_interval']).hours.do(run_process, scheduled_syncer,
                                                                          syncer_name=syncer_name)
                log.info(f"Added {syncer_name} syncer to schedule, syncing every {syncer_conf['sync_interval']} hours")

            # run schedule
            while True:
                try:
                    schedule.run_pending()
                except Exception:
                    log.exception("Unhandled exception occurred while processing scheduled tasks: ")
                time.sleep(1)
        elif conf.args['cmd'] == 'update_config':
            exit(0)
        else:
            log.error("Unknown command: %r", conf.args['cmd'])

    except KeyboardInterrupt:
        log.info("cloudplow was interrupted by Ctrl + C")
    except Exception:
        log.exception("Unexpected fatal exception occurred: ")
