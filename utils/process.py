import logging
import shlex
import subprocess

log = logging.getLogger("process")


def execute(command, callback=None, logs=True, shell=False):
    total_output = ''
    process = subprocess.Popen(shlex.split(command) if not shell else command, shell=shell, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    while True:
        output = process.stdout.readline().decode().strip()
        if process.poll() is not None:
            break
        if output and len(output):
            if logs:
                log.info(output)
            if callback:
                cancel = callback(output)
                if cancel:
                    if logs:
                        log.info("Callback requested termination, terminating...")
                    process.kill()
            else:
                total_output += "%s\n" % output

    if not callback:
        return total_output
    rc = process.poll()
    return rc


def popen(command, shell=False):
    try:
        data = subprocess.check_output(shlex.split(command) if not shell else command, shell=shell).decode().strip()
        return data
    except Exception:
        log.exception("Exception while executing process: ")
    return None
