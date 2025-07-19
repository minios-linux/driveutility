#!/usr/bin/python3

import os
import sys
import argparse
import stat
sys.path.append('/usr/lib/driveutility')
from mountutils import do_umount
import parted
import syslog

def get_source_size(source_path):
    """
    Get the size of the source. Handles both regular files and block devices.
    """
    try:
        # Get file status
        mode = os.stat(source_path).st_mode
        # Check if it's a block device
        if stat.S_ISBLK(mode):
            syslog.syslog(f"Source '{source_path}' is a block device. Using 'parted' to get size.")
            device = parted.getDevice(source_path)
            return float(device.getLength() * device.sectorSize)
        else:
            # It's a regular file, use os.path.getsize
            syslog.syslog(f"Source '{source_path}' is a regular file. Using 'os.path.getsize'.")
            return float(os.path.getsize(source_path))
    except Exception as e:
        syslog.syslog(f"Could not determine size of source '{source_path}': {e}")
        # Return 0 or raise an exception if size is critical
        return 0.0


def raw_write(source, target):
    syslog.syslog(f"Writing '{source}' on '{target}'")
    try:
        do_umount(target)
        bs = 1048576
        size = 0
        
        # <<< CHANGE: Use the new helper function to get the correct size
        total_size = get_source_size(source)
        if total_size == 0:
            syslog.syslog(f"Error: Source '{source}' has zero size or is inaccessible.")
            print("failed")
            exit(4)

        input = open(source, 'rb')

        # Check if the image can fit ... :)
        device = parted.getDevice(target)
        device_size = device.getLength() * device.sectorSize
        if device_size < total_size:
            input.close()
            print("nospace")
            exit(3)

        # Handle potential division by zero if total_size is very small, though unlikely now
        increment = total_size / 100 if total_size > 0 else 0

        written = 0
        output = open(target, 'wb')
        while True:
            buffer = input.read(bs)
            if len(buffer) == 0:
                break
            output.write(buffer)
            size = size + len(buffer)
            written = written + len(buffer)
            
            # <<< CHANGE: Avoid division by zero
            if total_size > 0:
                print(size / total_size)

            if increment > 0 and written >= increment:
                output.flush()
                os.fsync(output.fileno())
                written = 0

        output.flush()
        os.fsync(output.fileno())
        input.close()
        output.close()
        
        # A small tolerance for size comparison might be safer
        if abs(size - total_size) < bs:
            print("1.0")
            exit(0)
        else:
            syslog.syslog(f"Write failed: total size {total_size}, written size {size}")
            print("failed")
            exit(4)
            
    except Exception as e:
        syslog.syslog("An exception occured")
        syslog.syslog(str(e))
        print("failed")
        exit(4)

def main():
    # parse command line options
    try:
        parser = argparse.ArgumentParser(description="Write a disk image to a device",
                                         prog="driveutility-write",
                                         epilog="Example : driveutility-write -s /foo/image.iso -t /dev/sdj")
        parser.add_argument("-s", "--source", help="Source image file path", type=str, required=True)
        parser.add_argument("-t", "--target", help="Target device path", type=str, required=True)
        args = parser.parse_args()
    except Exception as e:
        print(e)
        sys.exit(2)

    raw_write(args.source, args.target)

if __name__ == "__main__":
    main()
