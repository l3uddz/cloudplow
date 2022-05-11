import logging
import shlex
import subprocess

log = logging.getLogger("process")


def execute(command, callback=None, logs=True, shell=False):
    total_output = ''
    process = subprocess.Popen(command if shell else shlex.split(command),
                               shell=shell,
                               stdout=subprocess.PIPE,
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
                        log.debug(f"Callback output {cancel}")
                    process.kill()
            else:
                total_output += "%s\n" % output

    if not callback:
        return total_output
    return process.poll()


def popen(command, shell=False):
    try:
        return subprocess.check_output(command if shell else shlex.split(command),
                                       shell=shell).decode().strip()

    except Exception:
        log.exception("Exception while executing process: ")
    return None
