import sys
from subprocess import call
import syslog

def do_umount(target):
        mounts = get_mounted(target)
        if mounts:
            syslog.syslog(f"Unmounting all partitions of {target}.")
        for mount in mounts:
            device = mount[0]
            syslog.syslog(f"Trying to unmount {device}...")
            try:
                retcode = call(f"umount {device}", shell=True)
                if retcode < 0:
                    error = str(retcode)
                    syslog.syslog(f"Error, umount {device} was terminated by signal {error}")
                    syslog.syslog(f"Continuing anyway - operation may fail if device is in use")
                else:
                    if retcode == 0:
                        syslog.syslog(f"{device} successfully unmounted")
                    else:
                        syslog.syslog(f"Warning, umount {device} returned {retcode}")
                        syslog.syslog(f"Continuing anyway - operation may fail if device is in use")
            except OSError as e:
                error = str(e)
                syslog.syslog(f"Execution failed: {error}")
                syslog.syslog(f"Continuing anyway - operation may fail if device is in use")


def get_mounted(target):
        try:
            lines = [line.strip("\n").split(" ") for line in open ("/etc/mtab", "r").readlines()]
            return [mount for mount in lines if mount[0].startswith(target)]
        except:
             syslog.syslog('Could not read mtab!')
             sys.exit(6)