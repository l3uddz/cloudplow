import logging
import time

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


def merge_dicts(*dicts):
    """ reference: https://stackoverflow.com/a/24745412 """
    d = {}
    for dict in dicts:
        for key in dict:
            try:
                d[key] = dict[key]
            except KeyError:
                pass
    return d


def get_nearest_less_element(data, num):
    """ reference: https://stackoverflow.com/a/7934624 """
    return data[str(num)] if str(num) in data else data[min(data.keys(), key=lambda k: abs(int(k) - num))]


def is_time_between(time_range, current_time=time.strftime('%H:%M')):
    """ reference: https://stackoverflow.com/a/45265202 """
    try:
        if time_range[1] < time_range[0]:
            return current_time >= time_range[0] or current_time <= time_range[1]
        return time_range[0] <= current_time <= time_range[1]
    except Exception:
        log.exception("Exception determining if current time was between the supplied range: ")
    return True
