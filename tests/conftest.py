"""
Pytest fixtures for driveutility tests.
"""
import os
import sys
import pytest
import tempfile

# Add lib directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_block_device(temp_dir):
    """Create a mock block device file for testing."""
    # Note: This won't be a real block device, just for path validation tests
    device_path = os.path.join(temp_dir, 'mock_device')
    with open(device_path, 'wb') as f:
        f.write(b'\x00' * 1024)
    return device_path


@pytest.fixture
def mock_mtab(temp_dir, monkeypatch):
    """Create a mock /etc/mtab file."""
    mtab_content = """/dev/sda1 / ext4 rw,relatime 0 0
/dev/sda2 /home ext4 rw,relatime 0 0
/dev/sdb1 /mnt/usb vfat rw,relatime 0 0
"""
    mtab_path = os.path.join(temp_dir, 'mtab')
    with open(mtab_path, 'w') as f:
        f.write(mtab_content)
    return mtab_path
