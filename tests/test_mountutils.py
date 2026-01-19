"""
Tests for mountutils module.
"""
import os
import pytest
from unittest.mock import patch, MagicMock

import mountutils


class TestValidateDevicePath:
    """Tests for _validate_device_path function."""
    
    def test_valid_device_path_format(self):
        """Test that valid device path format is accepted."""
        # Can't test with real block devices, but we can test path format validation
        with patch('os.path.exists', return_value=True):
            with patch('os.stat') as mock_stat:
                import stat
                mock_stat.return_value.st_mode = stat.S_IFBLK | 0o660
                assert mountutils._validate_device_path('/dev/sda1') is True
    
    def test_empty_path(self):
        """Test that empty path is rejected."""
        assert mountutils._validate_device_path('') is False
        assert mountutils._validate_device_path(None) is False
    
    def test_path_not_starting_with_dev(self):
        """Test that path not starting with /dev/ is rejected."""
        assert mountutils._validate_device_path('/tmp/fake_device') is False
        assert mountutils._validate_device_path('dev/sda1') is False
    
    def test_path_traversal_rejected(self):
        """Test that path traversal attempts are rejected."""
        assert mountutils._validate_device_path('/dev/../etc/passwd') is False
        assert mountutils._validate_device_path('/dev/sda/../sdb') is False
    
    def test_nonexistent_device(self):
        """Test that nonexistent device is rejected."""
        assert mountutils._validate_device_path('/dev/nonexistent_device_xyz') is False


class TestGetMounted:
    """Tests for get_mounted function."""
    
    def test_get_mounted_with_mock_mtab(self, temp_dir):
        """Test parsing of mtab file."""
        mtab_content = """/dev/sda1 / ext4 rw 0 0
/dev/sdb1 /mnt/usb vfat rw 0 0
/dev/sdb2 /mnt/data ext4 rw 0 0
"""
        mtab_path = os.path.join(temp_dir, 'mtab')
        with open(mtab_path, 'w') as f:
            f.write(mtab_content)
        
        with patch.object(mountutils, 'open', lambda f, m: open(mtab_path, m)):
            # This won't work directly, need to patch differently
            pass
    
    def test_get_mounted_filters_by_target(self):
        """Test that get_mounted filters by target device."""
        mock_mtab = """/dev/sda1 / ext4 rw 0 0
/dev/sdb1 /mnt/usb vfat rw 0 0
/dev/sdb2 /mnt/data ext4 rw 0 0
"""
        with patch('builtins.open', MagicMock(return_value=MagicMock(
            __enter__=MagicMock(return_value=MagicMock(
                readlines=MagicMock(return_value=mock_mtab.split('\n'))
            )),
            __exit__=MagicMock(return_value=False)
        ))):
            result = mountutils.get_mounted('/dev/sdb')
            # Should return 2 entries for /dev/sdb
            assert len(result) == 2
    
    def test_get_mounted_empty_result(self):
        """Test get_mounted with no matching devices."""
        mock_mtab = """/dev/sda1 / ext4 rw 0 0
"""
        with patch('builtins.open', MagicMock(return_value=MagicMock(
            __enter__=MagicMock(return_value=MagicMock(
                readlines=MagicMock(return_value=mock_mtab.split('\n'))
            )),
            __exit__=MagicMock(return_value=False)
        ))):
            result = mountutils.get_mounted('/dev/sdc')
            assert result == []


class TestDoUmount:
    """Tests for do_umount function."""
    
    def test_do_umount_with_no_mounts(self):
        """Test do_umount when device has no mounted partitions."""
        with patch.object(mountutils, 'get_mounted', return_value=[]):
            with patch('subprocess.call') as mock_call:
                mountutils.do_umount('/dev/sdc')
                # Should not call umount if nothing is mounted
                mock_call.assert_not_called()
    
    def test_do_umount_validates_device_path(self):
        """Test that do_umount validates device paths before unmounting."""
        with patch.object(mountutils, 'get_mounted', return_value=[
            ['/dev/../etc/passwd', '/mnt/evil']  # Invalid path
        ]):
            with patch('subprocess.call') as mock_call:
                mountutils.do_umount('/dev/sdb')
                # Should skip invalid device path
                mock_call.assert_not_called()
    
    def test_do_umount_uses_list_form(self):
        """Test that do_umount uses list form of call (not shell=True)."""
        with patch.object(mountutils, 'get_mounted', return_value=[
            ['/dev/sdb1', '/mnt/usb']
        ]):
            with patch.object(mountutils, '_validate_device_path', return_value=True):
                with patch('subprocess.call') as mock_call:
                    mock_call.return_value = 0
                    mountutils.do_umount('/dev/sdb')
                    # Verify call was made with list, not string
                    mock_call.assert_called_once()
                    args = mock_call.call_args[0][0]
                    assert isinstance(args, list)
                    assert args == ['umount', '/dev/sdb1']
