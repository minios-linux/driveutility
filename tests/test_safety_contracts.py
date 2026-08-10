import os
import sys
import types
from unittest.mock import patch

import pytest

try:
    import lz4.frame  # noqa: F401
except ImportError:
    lz4 = types.ModuleType("lz4")
    lz4.frame = types.ModuleType("lz4.frame")
    sys.modules["lz4"] = lz4
    sys.modules["lz4.frame"] = lz4.frame

import deviceutils
import mountutils
import raw_format
import raw_read
import raw_wipe
import raw_write


@pytest.mark.parametrize("partition,disk,expected", [
    ("/dev/sda1", "/dev/sda", True),
    ("/dev/sdaa1", "/dev/sda", False),
    ("/dev/nvme0n1p2", "/dev/nvme0n1", True),
    ("/dev/mmcblk0p1", "/dev/mmcblk0", True),
])
def test_partition_matching_is_exact(partition, disk, expected):
    assert deviceutils.is_same_device_or_partition(partition, disk) is expected


def test_format_stops_before_mutation_when_unmount_fails():
    with patch.object(raw_format, "_validate_device_path", return_value=True), \
            patch.object(raw_format, "_preflight_tools", return_value=True), \
            patch.object(raw_format, "do_umount",
                         side_effect=mountutils.UnmountError("busy")), \
            patch.object(raw_format, "execute") as execute:
        with pytest.raises(mountutils.UnmountError):
            raw_format.raw_format("/dev/sda", "ext4", "DATA", "1000", "1000")
        execute.assert_not_called()


def test_format_stops_before_unmount_when_tool_is_missing():
    with patch.object(raw_format, "_validate_device_path", return_value=True), \
            patch.object(raw_format, "_preflight_tools", return_value=False), \
            patch.object(raw_format, "do_umount") as unmount:
        with pytest.raises(SystemExit) as error:
            raw_format.raw_format("/dev/sda", "ext4", "DATA", "1000", "1000")
        assert error.value.code == 3
        unmount.assert_not_called()


@pytest.mark.parametrize("passes,size", [(0, None), (-1, None), (1, 0)])
def test_wipe_rejects_noop_parameters_before_unmount(passes, size):
    with patch.object(raw_wipe, "is_block_device", return_value=True), \
            patch.object(raw_wipe, "do_umount") as unmount:
        with pytest.raises(ValueError):
            raw_wipe.raw_wipe("/dev/sda", passes, "zero", False, size, "1M")
        unmount.assert_not_called()


def test_write_rejects_non_block_target_before_unmount():
    with patch.object(raw_write, "is_block_device", return_value=False), \
            patch.object(raw_write, "do_umount") as unmount:
        with pytest.raises(SystemExit) as error:
            raw_write.raw_write("/tmp/image", "/tmp/not-a-device")
        assert error.value.code == 4
        unmount.assert_not_called()


def test_read_refuses_existing_and_symlink_outputs(temp_dir):
    existing = os.path.join(temp_dir, "existing.img")
    with open(existing, "wb") as handle:
        handle.write(b"keep")

    with pytest.raises(FileExistsError):
        raw_read._open_exclusive_output(existing, os.geteuid(), os.getegid())
    with open(existing, "rb") as handle:
        assert handle.read() == b"keep"

    link = os.path.join(temp_dir, "link.img")
    os.symlink(existing, link)
    with pytest.raises(FileExistsError):
        raw_read._open_exclusive_output(link, os.geteuid(), os.getegid())
    with open(existing, "rb") as handle:
        assert handle.read() == b"keep"
