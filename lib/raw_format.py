#!/usr/bin/python3

import os
import re
import stat
from subprocess import call
import sys
import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mountutils import do_umount
import syslog

# Supported filesystem types
SUPPORTED_FILESYSTEMS = ("fat32", "exfat", "ntfs", "ext4")

# Volume label validation patterns
LABEL_PATTERNS = {
    "fat32": re.compile(r'^[A-Z0-9 _-]{0,11}$'),
    "exfat": re.compile(r'^[A-Za-z0-9 _-]{0,15}$'),
    "ntfs": re.compile(r'^[A-Za-z0-9 _-]{0,32}$'),
    "ext4": re.compile(r'^[A-Za-z0-9 _.-]{0,16}$'),
}


def _validate_device_path(device_path):
    """Validate that device_path is a valid block device."""
    if not device_path or not isinstance(device_path, str):
        syslog.syslog(f"Invalid device path: empty or not a string")
        return False
    # Must start with /dev/
    if not device_path.startswith('/dev/'):
        syslog.syslog(f"Invalid device path: must start with /dev/")
        return False
    # No path traversal
    if '..' in device_path:
        syslog.syslog(f"Invalid device path: path traversal detected")
        return False
    # Check if exists and is a block device
    try:
        if not os.path.exists(device_path):
            syslog.syslog(f"Device does not exist: {device_path}")
            return False
        mode = os.stat(device_path).st_mode
        if not stat.S_ISBLK(mode):
            syslog.syslog(f"Not a block device: {device_path}")
            return False
    except (OSError, IOError) as e:
        syslog.syslog(f"Cannot stat device {device_path}: {e}")
        return False
    return True


def _validate_volume_label(label, fstype):
    """Validate volume label for the given filesystem type."""
    if not label:
        return True  # Empty label is allowed
    pattern = LABEL_PATTERNS.get(fstype)
    if pattern and not pattern.match(label):
        syslog.syslog(f"Invalid volume label for {fstype}: {label}")
        return False
    return True


def execute(command):
    """Execute a command and check return code."""
    syslog.syslog(str(command))
    retcode = call(command)
    if retcode != 0:
        syslog.syslog(f"Command failed with exit code {retcode}: {command}")
        sys.exit(5)
    call(["sync"])


def raw_format(device_path, fstype, volume_label, uid, gid):
    """Format a storage device with the specified filesystem."""
    # Validate device path
    if not _validate_device_path(device_path):
        syslog.syslog(f"Refusing to format invalid device: {device_path}")
        sys.exit(1)

    # Validate filesystem type
    if fstype not in SUPPORTED_FILESYSTEMS:
        syslog.syslog(f"Unsupported filesystem: {fstype}")
        sys.exit(2)

    # Validate volume label
    if not _validate_volume_label(volume_label, fstype):
        syslog.syslog(f"Invalid volume label for {fstype}: {volume_label}")
        sys.exit(2)

    # Validate uid/gid
    try:
        uid = int(uid)
        gid = int(gid)
        if uid < 0 or gid < 0:
            raise ValueError("UID/GID must be non-negative")
    except (ValueError, TypeError) as e:
        syslog.syslog(f"Invalid UID/GID: {e}")
        sys.exit(2)

    do_umount(device_path)

    # Determine partition path (handle both /dev/sdX and /dev/nvmeXnY formats)
    if 'nvme' in device_path or 'mmcblk' in device_path:
        partition_path = f"{device_path}p1"
    else:
        partition_path = f"{device_path}1"

    # Map filesystem to partition type
    partition_types = {
        "fat32": "fat32",
        "exfat": "ntfs",
        "ntfs": "ntfs",
        "ext4": "ext4",
    }
    partition_type = partition_types[fstype]

    # First erase MBR and partition table, if any
    execute(["dd", "if=/dev/zero", f"of={device_path}", "bs=512", "count=1"])

    # Make the partition table
    execute(["parted", device_path, "mktable", "msdos"])

    # Make a partition (primary, with FS ID, starting at 1MB & using 100% of space).
    # If it starts at 0% or 0MB, it's not aligned to MB's and complains
    execute(["parted", device_path, "mkpart", "primary", partition_type, "1", "100%"])

    # Call wipefs on the new partitions to avoid problems with old filesystem signatures
    execute(["wipefs", "-a", partition_path, "--force"])

    # Format the FS on the partition
    if fstype == "fat32":
        execute(["mkdosfs", "-F", "32", "-n", volume_label, partition_path])
    elif fstype == "exfat":
        execute(["mkfs.exfat", "-n", volume_label, partition_path])
    elif fstype == "ntfs":
        execute(["mkntfs", "-f", "-L", volume_label, partition_path])
    elif fstype == "ext4":
        execute(["mkfs.ext4", "-E", f"root_owner={uid}:{gid}", "-L", volume_label, partition_path])

    # Exit
    sys.exit(0)

def main():
    # parse command line options
    try:
        parser = argparse.ArgumentParser(
            description="Format a storage device",
            prog="driveutility-format",
            epilog='Example: driveutility-format -d /dev/sdj -f fat32 -l "STORAGE" -u 1000 -g 1000'
        )
        parser.add_argument("-d", "--device", help="Device path", type=str, required=True)
        parser.add_argument("-f", "--filesystem", help="File system type", action="store",
                            type=str, choices=SUPPORTED_FILESYSTEMS, required=True)
        parser.add_argument("-u", "--uid", help="UID of the user", type=str, required=True)
        parser.add_argument("-g", "--gid", help="GID of the user", type=str, required=True)
        parser.add_argument("label", help="Volume label", type=str, nargs="*")
        args = parser.parse_args()
        args.label = " ".join(args.label)
    except Exception as e:
        print(f"Error parsing arguments: {e}", file=sys.stderr)
        sys.exit(2)

    raw_format(args.device, args.filesystem, args.label, args.uid, args.gid)

if __name__ == "__main__":
    main()
