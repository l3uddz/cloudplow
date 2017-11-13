import logging

log = logging.getLogger("misc")


def seconds_to_string(seconds):
    """ reference: https://codereview.stackexchange.com/a/120595 """
    resp = ''
    try:
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        if days:
            resp += '%d days' % days
        if hours:
            if len(resp):
                resp += ', '
            resp += '%d hours' % hours
        if minutes:
            if len(resp):
                resp += ', '
            resp += '%d minutes' % minutes
        if seconds:
            if len(resp):
                resp += ' and '
            resp += '%d seconds' % seconds
    except Exception:
        log.exception("Exception occurred converting %d seconds to readable string: ", seconds)
        resp = '%d seconds' % seconds
    return resp
