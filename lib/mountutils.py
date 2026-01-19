import os
import stat
import sys
from subprocess import call
import syslog


def _validate_device_path(device):
    """Validate that device path is a valid block device."""
    if not device or not isinstance(device, str):
        return False
    # Must start with /dev/
    if not device.startswith('/dev/'):
        return False
    # No path traversal
    if '..' in device:
        return False
    # Check if exists and is a block device
    try:
        if os.path.exists(device):
            mode = os.stat(device).st_mode
            return stat.S_ISBLK(mode)
    except (OSError, IOError):
        pass
    return False


def do_umount(target):
    """Unmount all partitions of a target device."""
    mounts = get_mounted(target)
    if mounts:
        syslog.syslog(f"Unmounting all partitions of {target}.")
    for mount in mounts:
        device = mount[0]
        # Validate device path to prevent command injection
        if not _validate_device_path(device):
            syslog.syslog(f"Invalid device path: {device}, skipping")
            continue
        syslog.syslog(f"Trying to unmount {device}...")
        try:
            # Use list form to prevent shell injection (no shell=True)
            retcode = call(["umount", device])
            if retcode < 0:
                error = str(retcode)
                syslog.syslog(f"Error, umount {device} was terminated by signal {error}")
                syslog.syslog("Continuing anyway - operation may fail if device is in use")
            else:
                if retcode == 0:
                    syslog.syslog(f"{device} successfully unmounted")
                else:
                    syslog.syslog(f"Warning, umount {device} returned {retcode}")
                    syslog.syslog("Continuing anyway - operation may fail if device is in use")
        except OSError as e:
            error = str(e)
            syslog.syslog(f"Execution failed: {error}")
            syslog.syslog("Continuing anyway - operation may fail if device is in use")


def get_mounted(target):
    """Get list of mounted partitions for a target device."""
    try:
        with open("/etc/mtab", "r") as f:
            lines = [line.strip("\n").split(" ") for line in f.readlines()]
        return [mount for mount in lines if mount[0].startswith(target)]
    except (IOError, OSError) as e:
        syslog.syslog(f'Could not read mtab: {e}')
        sys.exit(6)