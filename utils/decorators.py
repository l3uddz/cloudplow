import logging
import os
import timeit

from . import misc

log = logging.getLogger("decorators")


def timed(method):
    def timer(*args, **kw):
        start_time = timeit.default_timer()
        result = method(*args, **kw)
        time_taken = timeit.default_timer() - start_time
        try:
            log.info("%r from %r finished in %s", method.__name__,
                     os.path.basename(method.__code__.co_filename),
                     misc.seconds_to_string(time_taken))
        except Exception:
            log.exception("Exception while logging time taken to run function: ")
        return result

    return timer
