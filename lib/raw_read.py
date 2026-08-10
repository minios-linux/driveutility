#!/usr/bin/python3

import os
import pwd
import sys
import argparse
import stat
import syslog
import gzip
import bz2
import lzma
from deviceutils import is_block_device
try:
    import zstandard
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False
import lz4.frame


class _LZ4FrameWriter:
    """LZ4 compressed file writer compatible with lz4 < 0.19 (no lz4.frame.open)."""

    def __init__(self, fileobj):
        self._file = fileobj
        self._compressor = None
        self._closed = False

    def __enter__(self):
        self._compressor = lz4.frame.LZ4FrameCompressor()
        self._file.write(self._compressor.compress_begin())
        return self

    def write(self, data):
        self._file.write(self._compressor.compress(data))

    def flush(self):
        self._file.flush()

    def __exit__(self, *args):
        if not self._closed and self._compressor and self._file:
            self._file.write(self._compressor.flush())
            self._closed = True
        return False


def _resolve_output_owner(requested_uid, requested_gid):
    """Bind a pkexec output to its authenticated desktop caller."""
    pkexec_uid = os.environ.get("PKEXEC_UID")
    if os.geteuid() == 0 and pkexec_uid is not None:
        try:
            owner_uid = int(pkexec_uid)
            owner_gid = pwd.getpwuid(owner_uid).pw_gid
        except (ValueError, KeyError, OverflowError):
            raise PermissionError("Invalid PKEXEC_UID")
        if requested_uid not in (-1, owner_uid):
            raise PermissionError("Requested UID does not match PKEXEC_UID")
        if requested_gid not in (-1, owner_gid):
            raise PermissionError("Requested GID does not match PKEXEC_UID")
        return owner_uid, owner_gid

    if os.geteuid() != 0:
        owner_uid = os.geteuid()
        owner_gid = os.getegid()
        if requested_uid not in (-1, owner_uid):
            raise PermissionError("Cannot create output for another UID")
        if requested_gid not in (-1, owner_gid):
            raise PermissionError("Cannot create output for another GID")
        return owner_uid, owner_gid

    # Direct root use has no unprivileged pkexec identity to bind to.
    owner_uid = 0 if requested_uid == -1 else requested_uid
    owner_gid = 0 if requested_gid == -1 else requested_gid
    if owner_uid < 0 or owner_gid < 0:
        raise PermissionError("Invalid output owner")
    return owner_uid, owner_gid


def _open_exclusive_output(path, uid, gid):
    """Create a new regular output without following or replacing anything."""
    if not os.path.isabs(path):
        raise ValueError("Output path must be absolute")
    parent = os.path.dirname(path)
    basename = os.path.basename(path)
    if basename in ('', '.', '..'):
        raise ValueError("Invalid output filename")

    parent_flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
    parent_flags |= getattr(os, 'O_CLOEXEC', 0)
    parent_fd = os.open(parent, parent_flags)
    parent_stat = os.fstat(parent_fd)
    if uid != 0:
        if uid == parent_stat.st_uid:
            permissions = (parent_stat.st_mode >> 6) & 0o7
        elif gid == parent_stat.st_gid:
            permissions = (parent_stat.st_mode >> 3) & 0o7
        else:
            permissions = parent_stat.st_mode & 0o7
        if permissions & 0o3 != 0o3:
            os.close(parent_fd)
            raise PermissionError(
                "PKEXEC_UID cannot create files in the output directory")

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, 'O_CLOEXEC', 0)
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    fd = None
    identity = None
    try:
        fd = os.open(basename, flags, 0o600, dir_fd=parent_fd)
        identity = os.fstat(fd)
        if not stat.S_ISREG(identity.st_mode):
            raise ValueError("Output is not a regular file")
        os.fchown(fd, uid, gid)
        output = os.fdopen(fd, 'wb')
        fd = None
        os.close(parent_fd)
        parent_fd = None
        return output
    except Exception:
        if fd is not None:
            os.close(fd)
        if parent_fd is not None and identity is not None:
            try:
                current = os.stat(basename, dir_fd=parent_fd,
                                  follow_symlinks=False)
                if (stat.S_ISREG(current.st_mode)
                        and current.st_dev == identity.st_dev
                        and current.st_ino == identity.st_ino):
                    os.unlink(basename, dir_fd=parent_fd)
            except OSError:
                pass
        if parent_fd is not None:
            os.close(parent_fd)
        raise


def _remove_created_output(path, identity):
    """Remove only the exact partial file created by this process."""
    try:
        current = os.lstat(path)
        if (stat.S_ISREG(current.st_mode)
                and current.st_dev == identity.st_dev
                and current.st_ino == identity.st_ino):
            os.unlink(path)
    except OSError:
        pass


def _open_block_source(source_path):
    source_fd = os.open(source_path,
                        os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0))
    if not stat.S_ISBLK(os.fstat(source_fd).st_mode):
        os.close(source_fd)
        raise ValueError("Source is not a block device")
    return os.fdopen(source_fd, 'rb')


def _open_block_size(source):
    size = os.lseek(source.fileno(), 0, os.SEEK_END)
    os.lseek(source.fileno(), 0, os.SEEK_SET)
    return float(size)

def get_source_size(source_path):
    """
    Get the size of a source block device.
    """
    try:
        with _open_block_source(source_path) as source:
            return _open_block_size(source)
    except Exception as e:
        syslog.syslog(f"Could not determine size of source '{source_path}': {e}")
        return 0.0

def get_compression_writer(target_file, compression_method):
    """
    Returns the appropriate file opening context manager for writing based on the compression method.
    """
    if compression_method == 'gzip':
        return gzip.GzipFile(fileobj=target_file, mode='wb')
    elif compression_method == 'bzip2':
        return bz2.BZ2File(target_file, 'wb')
    elif compression_method == 'xz':
        return lzma.LZMAFile(target_file, 'wb')
    elif compression_method == 'lz4':
        return _LZ4FrameWriter(target_file)
    elif compression_method == 'zstd':
        if not ZSTD_AVAILABLE:
            raise ImportError("zstandard module not available")
        cctx = zstandard.ZstdCompressor()
        return cctx.stream_writer(target_file)
    else:
        return target_file

def raw_read(source, target, compression, uid, gid):
    """
    Reads data from a source device and writes it to a target image file, with optional compression.
    """
    if not is_block_device(source):
        print("Error: The source must be a block device.", file=sys.stderr)
        print("failed")
        exit(4)

    owner_uid, owner_gid = _resolve_output_owner(uid, gid)

    if compression:
        # Append the correct extension
        ext_map = {'gzip': 'gz', 'bzip2': 'bz2', 'xz': 'xz', 'lz4': 'lz4', 'zstd': 'zst'}
        target += '.' + ext_map.get(compression, '')
        syslog.syslog(f"Creating compressed ({compression}) image of '{source}' at '{target}'")
    else:
        syslog.syslog(f"Creating image of '{source}' at '{target}'")
        
    try:
        bs = 1048576  # 1MB block size

        input_file = _open_block_source(source)
        total_size = _open_block_size(input_file)

        if total_size == 0:
            input_file.close()
            syslog.syslog(f"Error: Source '{source}' has zero size or is inaccessible.")
            print("failed")
            exit(4)

        target_file = _open_exclusive_output(target, owner_uid, owner_gid)
        target_identity = os.fstat(target_file.fileno())

        def copy_to(output_file):
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

            return size

        try:
            with input_file, target_file:
                output_file = get_compression_writer(target_file, compression)
                if output_file is target_file:
                    size = copy_to(output_file)
                else:
                    with output_file:
                        size = copy_to(output_file)
        except BaseException:
            _remove_created_output(target, target_identity)
            raise

        # Final size comparison
        if abs(size - total_size) < bs:
            print("1.0")
            syslog.syslog(f"Successfully created image of '{source}' at '{target}'.")
            
            exit(0)
        else:
            syslog.syslog(f"Image creation failed: total size {total_size}, written size {size}")
            _remove_created_output(target, target_identity)
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
    compression_choices = ['gzip', 'bzip2', 'xz', 'lz4']
    compression_help = "Compression method (gzip, bzip2, xz, lz4"
    if ZSTD_AVAILABLE:
        compression_choices.append('zstd')
        compression_help += ", zstd"
    compression_help += ")"
    
    parser = argparse.ArgumentParser(description="Create a disk image from a device.",
                                     prog="driveutility-read",
                                     epilog="Example: driveutility-read -s /dev/sdj -t /foo/image -c zstd")
    parser.add_argument("-s", "--source", help="Source device path", type=str, required=True)
    parser.add_argument("-t", "--target", help="Target image file path (extension is added automatically)", type=str, required=True)
    parser.add_argument("-c", "--compression", help=compression_help, type=str, choices=compression_choices)
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
