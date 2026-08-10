import os
from subprocess import call
import syslog

from deviceutils import is_block_device, is_same_device_or_partition


class UnmountError(RuntimeError):
    pass


def _validate_device_path(device):
    """Validate that device path is a valid block device."""
    return is_block_device(device)


def do_umount(target):
    """Unmount a target and its partitions, then verify that they stayed down."""
    if not _validate_device_path(target):
        raise UnmountError("Invalid target block device: {}".format(target))

    mounts = get_mounted(target)
    if mounts:
        syslog.syslog(f"Unmounting all partitions of {target}.")
    for mount in mounts:
        device = mount[0]
        # Validate device path to prevent command injection
        if not _validate_device_path(device):
            raise UnmountError("Invalid mounted device path: {}".format(device))
        syslog.syslog(f"Trying to unmount {device}...")
        try:
            # Use list form to prevent shell injection (no shell=True)
            retcode = call(["umount", device])
            if retcode != 0:
                raise UnmountError(
                    "umount {} returned {}".format(device, retcode))
            syslog.syslog(f"{device} successfully unmounted")
        except OSError as e:
            raise UnmountError(
                "Could not execute umount for {}: {}".format(device, e))

    remaining = get_mounted(target)
    if remaining:
        devices = ", ".join(mount[0] for mount in remaining)
        raise UnmountError(
            "Device is still mounted after unmount: {}".format(devices))
    return True


def get_mounted(target):
    """Get list of mounted partitions for a target device."""
    try:
        with open("/etc/mtab", "r") as f:
            lines = [line.strip("\n").split(" ") for line in f.readlines()]
        return [mount for mount in lines
                if mount and is_same_device_or_partition(mount[0], target)]
    except (IOError, OSError) as e:
        syslog.syslog(f'Could not read mtab: {e}')
        raise UnmountError("Could not read mounted-device state: {}".format(e))
