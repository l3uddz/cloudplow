import logging
import os
import sys

try:
    from git import Repo
except ImportError:
    sys.exit("You are missing the GitPython requirement.")

log = logging.getLogger("git")

repo = Repo.init(os.path.dirname(os.path.realpath(sys.argv[0])))


def active_branch():
    global repo

    try:
        branch = repo.active_branch.name
        return branch

    except Exception as ex:
        log.exception("Exception retrieving current branch: ")
    return 'Unknown'


def latest_version():
    global repo

    try:
        fetch_info = repo.remotes.origin.fetch()
        return str(fetch_info[0].commit)

    except Exception as ex:
        log.exception("Exception retrieving the latest commit id: ")
    return 'Unknown'


def current_version():
    global repo

    try:
        result = repo.active_branch.commit
        return str(result)

    except Exception as ex:
        log.exception("Exception retrieving the current commit id: ")
    return 'Unknown'


def missing_commits(using_version):
    global repo
    missing = 0

    try:
        for commit in repo.iter_commits():
            if str(commit) == using_version:
                break
            missing += 1

    except Exception as ex:
        log.exception("Exception iterating commits: ")
    return missing


def check_version():
    current = current_version()
    latest = latest_version()

    if current == 'Unknown' or latest == 'Unknown':
        log.debug("Unable to check version due to failure to determine current/latest commits")
        return

    if current != latest:
        log.debug("You are NOT using the latest %s: %s", active_branch(), latest)
    else:
        log.debug("You are using the latest %s: %s", active_branch(), latest)
    return
