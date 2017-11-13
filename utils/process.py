import logging
import shlex
import subprocess

log = logging.getLogger("process")


def execute(command, callback=None, logs=True):
    total_output = ''
    process = subprocess.Popen(shlex.split(command), shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    while True:
        output = str(process.stdout.readline()).lstrip('b').replace('\\n', '')
        if process.poll() is not None:
            break
        if output and len(output) > 6:
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
