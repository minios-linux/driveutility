#!/usr/bin/python3

import os
import sys
import argparse
import stat
import syslog
import parted
import gzip
import bz2
import lzma
import zstandard
import lz4.frame

def get_source_size(source_path):
    """
    Get the size of the source. Handles both regular files and block devices.
    """
    try:
        mode = os.stat(source_path).st_mode
        if stat.S_ISBLK(mode):
            syslog.syslog(f"Source '{source_path}' is a block device. Using 'parted' to get size.")
            device = parted.getDevice(source_path)
            return float(device.getLength() * device.sectorSize)
        else:
            syslog.syslog(f"Source '{source_path}' is a regular file. Using 'os.path.getsize'.")
            return float(os.path.getsize(source_path))
    except Exception as e:
        syslog.syslog(f"Could not determine size of source '{source_path}': {e}")
        return 0.0

def get_compression_writer(target_path, compression_method):
    """
    Returns the appropriate file opening context manager for writing based on the compression method.
    """
    if compression_method == 'gzip':
        return gzip.open(target_path, 'wb')
    elif compression_method == 'bzip2':
        return bz2.open(target_path, 'wb')
    elif compression_method == 'xz':
        return lzma.open(target_path, 'wb')
    elif compression_method == 'lz4':
        return lz4.frame.open(target_path, 'wb')
    elif compression_method == 'zstd':
        # zstandard requires wrapping a file object
        f = open(target_path, 'wb')
        cctx = zstandard.ZstdCompressor()
        return cctx.stream_writer(f)
    else:
        return open(target_path, 'wb')

def raw_read(source, target, compression, uid, gid):
    """
    Reads data from a source device and writes it to a target image file, with optional compression.
    """
    if compression:
        # Append the correct extension
        ext_map = {'gzip': 'gz', 'bzip2': 'bz2', 'xz': 'xz', 'lz4': 'lz4', 'zstd': 'zst'}
        target += '.' + ext_map.get(compression, '')
        syslog.syslog(f"Creating compressed ({compression}) image of '{source}' at '{target}'")
    else:
        syslog.syslog(f"Creating image of '{source}' at '{target}'")
        
    try:
        bs = 1048576  # 1MB block size
        total_size = get_source_size(source)

        if total_size == 0:
            syslog.syslog(f"Error: Source '{source}' has zero size or is inaccessible.")
            print("failed")
            exit(4)

        with open(source, 'rb') as input_file, \
             get_compression_writer(target, compression) as output_file:
            
            size = 0
            increment = total_size / 100 if total_size > 0 else 0
            read_since_flush = 0

            while True:
                buffer = input_file.read(bs)
                if not buffer:
                    break
                
                output_file.write(buffer)
                size += len(buffer)
                read_since_flush += len(buffer)

                if total_size > 0:
                    print(size / total_size)

                # Flushing is important for progress monitoring
                if increment > 0 and read_since_flush >= increment:
                    if hasattr(output_file, 'flush'):
                        output_file.flush()
                    # os.fsync is not applicable to all compression stream objects
                    read_since_flush = 0
            
            if hasattr(output_file, 'flush'):
                output_file.flush()

        # Final size comparison
        if abs(size - total_size) < bs:
            print("1.0")
            syslog.syslog(f"Successfully created image of '{source}' at '{target}'.")
            
            # Change file ownership if uid and gid are provided
            if uid != -1 and gid != -1:
                try:
                    os.chown(target, uid, gid)
                    syslog.syslog(f"Changed ownership of '{target}' to {uid}:{gid}")
                except Exception as e:
                    syslog.syslog(f"Failed to change ownership of '{target}': {e}")

            exit(0)
        else:
            syslog.syslog(f"Image creation failed: total size {total_size}, written size {size}")
            print("failed")
            exit(4)

    except Exception as e:
        syslog.syslog(f"An exception occurred: {e}")
        # Print the exception to stderr for easier debugging
        print(f"Error: {e}", file=sys.stderr)
        print("failed")
        exit(4)

def main():
    """
    Parses command line arguments and initiates the disk imaging process.
    """
    parser = argparse.ArgumentParser(description="Create a disk image from a device.",
                                     prog="driveutility-read",
                                     epilog="Example: driveutility-read -s /dev/sdj -t /foo/image -c zstd")
    parser.add_argument("-s", "--source", help="Source device path", type=str, required=True)
    parser.add_argument("-t", "--target", help="Target image file path (extension is added automatically)", type=str, required=True)
    parser.add_argument("-c", "--compression", help="Compression method (gzip, bzip2, xz, lz4, zstd)", type=str, choices=['gzip', 'bzip2', 'xz', 'lz4', 'zstd'])
    parser.add_argument("-u", "--uid", help="User ID to own the target file", type=int, default=-1)
    parser.add_argument("-g", "--gid", help="Group ID to own the target file", type=int, default=-1)
    
    try:
        args = parser.parse_args()
        # Prevent user from adding their own extension if compression is used
        if args.compression and any(args.target.endswith(ext) for ext in ['.gz', '.bz2', '.xz', '.lz4', '.zst']):
             print(f"Warning: Target filename should not include a compression extension when using -c.", file=sys.stderr)
             base, _ = os.path.splitext(args.target)
             args.target = base

        raw_read(args.source, args.target, args.compression, args.uid, args.gid)
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()