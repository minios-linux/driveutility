"""
Tests for raw_format module.
"""
import os
import pytest
from unittest.mock import patch, MagicMock

import raw_format


class TestValidateDevicePath:
    """Tests for device path validation in raw_format."""
    
    def test_rejects_non_dev_path(self):
        """Test that paths not starting with /dev/ are rejected."""
        with patch('syslog.syslog'):
            assert raw_format._validate_device_path('/tmp/fake') is False
    
    def test_rejects_path_traversal(self):
        """Test that path traversal is rejected."""
        with patch('syslog.syslog'):
            assert raw_format._validate_device_path('/dev/../etc/passwd') is False
    
    def test_rejects_empty_path(self):
        """Test that empty paths are rejected."""
        with patch('syslog.syslog'):
            assert raw_format._validate_device_path('') is False
            assert raw_format._validate_device_path(None) is False


class TestValidateVolumeLabel:
    """Tests for volume label validation."""
    
    @pytest.mark.parametrize("label,fstype,expected", [
        ("MYUSB", "fat32", True),
        ("MY USB", "fat32", True),
        ("", "fat32", True),  # Empty allowed
        ("my_usb", "ext4", True),
        ("my-usb", "ntfs", True),
        ("A" * 12, "fat32", False),  # Too long for FAT32 (max 11)
        ("A" * 17, "exfat", False),  # Too long for exFAT (max 15)
    ])
    def test_volume_label_validation(self, label, fstype, expected):
        """Test volume label validation for different filesystems."""
        result = raw_format._validate_volume_label(label, fstype)
        assert result == expected


class TestExecute:
    """Tests for execute function."""
    
    def test_execute_checks_return_code(self):
        """Test that execute checks command return code."""
        with patch('syslog.syslog'):
            with patch('subprocess.call', return_value=1) as mock_call:
                with pytest.raises(SystemExit) as exc_info:
                    raw_format.execute(['false'])
                assert exc_info.value.code == 5
    
    def test_execute_calls_sync(self):
        """Test that execute calls sync after command."""
        with patch('syslog.syslog'):
            with patch('subprocess.call', return_value=0) as mock_call:
                raw_format.execute(['true'])
                # Should be called twice: once for command, once for sync
                assert mock_call.call_count == 2
                assert mock_call.call_args_list[1][0][0] == ['sync']


class TestRawFormat:
    """Tests for raw_format function."""
    
    def test_raw_format_validates_device(self):
        """Test that raw_format validates device path."""
        with patch('syslog.syslog'):
            with pytest.raises(SystemExit) as exc_info:
                raw_format.raw_format('/tmp/not_a_device', 'ext4', 'TEST', '1000', '1000')
            assert exc_info.value.code == 1
    
    def test_raw_format_validates_fstype(self):
        """Test that raw_format validates filesystem type."""
        with patch('syslog.syslog'):
            with patch.object(raw_format, '_validate_device_path', return_value=True):
                with patch.object(raw_format, 'do_umount'):
                    with pytest.raises(SystemExit) as exc_info:
                        raw_format.raw_format('/dev/sdb', 'invalid_fs', 'TEST', '1000', '1000')
                    assert exc_info.value.code == 2
    
    def test_raw_format_validates_uid_gid(self):
        """Test that raw_format validates UID/GID."""
        with patch('syslog.syslog'):
            with patch.object(raw_format, '_validate_device_path', return_value=True):
                with patch.object(raw_format, 'do_umount'):
                    with pytest.raises(SystemExit) as exc_info:
                        raw_format.raw_format('/dev/sdb', 'ext4', 'TEST', 'not_a_number', '1000')
                    assert exc_info.value.code == 2
    
    def test_raw_format_handles_nvme_partition_path(self):
        """Test that raw_format correctly handles NVMe partition paths."""
        with patch('syslog.syslog'):
            with patch.object(raw_format, '_validate_device_path', return_value=True):
                with patch.object(raw_format, 'do_umount'):
                    with patch.object(raw_format, 'execute') as mock_execute:
                        with patch('sys.exit'):
                            # We can't fully test this without mocking everything,
                            # but we can verify the function is called
                            try:
                                raw_format.raw_format('/dev/nvme0n1', 'ext4', 'TEST', '1000', '1000')
                            except SystemExit:
                                pass
                            # Check that partition path uses 'p1' for NVMe
                            calls = mock_execute.call_args_list
                            # Look for mkfs call with partition path
                            for call in calls:
                                args = call[0][0]
                                if 'mkfs' in str(args):
                                    assert any('nvme0n1p1' in str(arg) for arg in args)
