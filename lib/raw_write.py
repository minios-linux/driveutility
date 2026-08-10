#!/usr/bin/python3

import os
import sys
import argparse
import stat
sys.path.append('/usr/lib/driveutility')
from deviceutils import is_block_device
from mountutils import do_umount
import syslog
import gzip
import bz2
import lzma
try:
    import zstandard
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False
import lz4.frame


class _LZ4FrameReader:
    """Bounded streaming reader for Bionic's pre-lz4.frame.open API."""

    _COMPRESSED_CHUNK_SIZE = 1024 * 1024

    def __init__(self, path):
        self._file = open(path, 'rb')
        self._decompressor = lz4.frame.LZ4FrameDecompressor()
        self._buffer = bytearray()
        self._eof = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False

    def close(self):
        if self._file is not None:
            self._file.close()
            self._file = None

    def read(self, size=-1):
        if size is None or size < 0:
            chunks = [bytes(self._buffer)]
            self._buffer.clear()
            while not self._eof:
                chunks.append(self._read_compressed_chunk())
            return b''.join(chunks)

        while len(self._buffer) < size and not self._eof:
            self._buffer.extend(self._read_compressed_chunk())
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    def _read_compressed_chunk(self):
        compressed = self._file.read(self._COMPRESSED_CHUNK_SIZE)
        if not compressed:
            self._eof = True
            return b''
        return self._decompressor.decompress(compressed)


def _lz4_open_compat(path, mode):
    """Open LZ4 input without loading the complete image on old python3-lz4."""
    if hasattr(lz4.frame, 'open'):
        return lz4.frame.open(path, mode)
    syslog.syslog("lz4.frame.open not available, using streaming decompression")
    return _LZ4FrameReader(path)


def _zstd_open_compat(path, mode):
    """Open a Zstandard file for reading."""
    f = open(path, 'rb')
    return zstandard.ZstdDecompressor().stream_reader(f)


# Magic numbers used to identify file types by their headers
MAGIC_NUMBERS = {
    b'\x1f\x8b': ('gzip', gzip.open),
    b'BZh': ('bzip2', bz2.open),
    b'\xfd7zXZ\x00': ('xz', lzma.open),
    b'\x04"M\x18': ('lz4', _lz4_open_compat),
}

if ZSTD_AVAILABLE:
    MAGIC_NUMBERS[b'(\xb5/\xfd'] = ('zstd', _zstd_open_compat)

def get_opener_by_magic(file_path):
    """
    Detects compression type by reading the file's magic number.
    Returns the appropriate opening function and the compression method name.
    """
    try:
        with open(file_path, 'rb') as f:
            header = f.read(16) # Read enough bytes to identify any of the formats
            for magic, (name, opener) in MAGIC_NUMBERS.items():
                if header.startswith(magic):
                    syslog.syslog(f"Detected {name} compression for file '{file_path}'")
                    return opener, name
    except IOError as e:
        syslog.syslog(f"Error reading file header for {file_path}: {e}")
        return None, None

    # If no magic number matches, assume it's an uncompressed raw file
    syslog.syslog(f"No compression detected for '{file_path}'. Treating as raw image.")
    return open, None

def raw_write(source, target):
    if not is_block_device(target):
        print("Error: The target must be a block device.", file=sys.stderr)
        print("failed")
        exit(4)

    opener, compression_method = get_opener_by_magic(source)

    if opener is None:
        print("failed")
        exit(4)

    if compression_method:
        syslog.syslog(f"Writing compressed ({compression_method}) image '{source}' to '{target}'")
    else:
        syslog.syslog(f"Writing raw image '{source}' to '{target}'")
        
    try:
        do_umount(target)
        bs = 1048576 # 1MB block size
        size = 0

        # Open first and validate the descriptor too, closing the path-race
        # window between the initial block-device check and the write.
        target_fd = os.open(target,
                            os.O_WRONLY | getattr(os, 'O_CLOEXEC', 0))
        if not stat.S_ISBLK(os.fstat(target_fd).st_mode):
            os.close(target_fd)
            raise ValueError("The opened target is not a block device")
        output_file = os.fdopen(target_fd, 'wb')
        
        # Check available space on target device
        # This is a best-effort check for uncompressed files only.
        # For compressed files, we cannot know the uncompressed size beforehand.
        if not compression_method:
            source_size = os.path.getsize(source)
            if source_size == 0:
                syslog.syslog(f"Error: Source '{source}' has zero size or is inaccessible.")
                print("failed")
                exit(4)
            
            device_size = os.lseek(output_file.fileno(), 0, os.SEEK_END)
            os.lseek(output_file.fileno(), 0, os.SEEK_SET)
            if device_size < source_size:
                output_file.close()
                syslog.syslog(f"Error: Not enough space on target '{target}'. Required: {source_size}, Available: {device_size}")
                print("nospace")
                exit(3)
        
        # For compressed files, progress reporting based on output size is the only option.
        if compression_method:
            syslog.syslog("Progress reporting is not available for compressed images.")

        input_stream = opener(source, 'rb')

        with input_stream, output_file:
            while True:
                buffer = input_stream.read(bs)
                if not buffer:
                    break
                output_file.write(buffer)
                size += len(buffer)
            
            output_file.flush()
            os.fsync(output_file.fileno())

        syslog.syslog(f"Write finished. Total bytes written: {size}")
        print("1.0") # Assume success if no exceptions were thrown
        exit(0)
            
    except Exception as e:
        syslog.syslog(f"An exception occurred: {e}")
        print(f"Error: {e}", file=sys.stderr)
        print("failed")
        exit(4)

def main():
    parser = argparse.ArgumentParser(description="Write a disk image to a device. Automatically detects compression.",
                                     prog="driveutility-write",
                                     epilog="Example: driveutility-write -s /foo/image.zst -t /dev/sdj")
    parser.add_argument("-s", "--source", help="Source image file path (can be raw or compressed)", type=str, required=True)
    parser.add_argument("-t", "--target", help="Target device path", type=str, required=True)
    
    try:
        args = parser.parse_args()
        if not os.path.exists(args.source):
            syslog.syslog(f"Source file not found: {args.source}")
            print("failed")
            exit(4)

        raw_write(args.source, args.target)
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
