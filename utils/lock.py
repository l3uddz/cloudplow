import logging
import os
import sys

import lockfile

log = logging.getLogger("lock")
lock_folder = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), 'locks')


def ensure_lock_folder():
    # ensure lock folder exists, otherwise create it
    try:
        if not os.path.exists(lock_folder):
            os.mkdir(lock_folder)
            log.info(f"Created lock folder: {lock_folder}")
    except Exception:
        log.exception(f"Exception verifying/creating lock folder {lock_folder}: ")
        sys.exit(1)


def upload():
    return lockfile.LockFile(os.path.join(lock_folder, 'upload'))


def sync():
    return lockfile.LockFile(os.path.join(lock_folder, 'sync'))


def hidden():
    return lockfile.LockFile(os.path.join(lock_folder, 'hidden'))
