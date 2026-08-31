from unittest.mock import patch

import pytest

import raw_wipe
import wipeutils


def test_nvme_capabilities_are_decoded_from_identify_controller():
    identify = {"oacs": 0x2, "fna": 0x7, "nn": 2}
    with patch.object(wipeutils, "nvme_cli_path", return_value="/usr/sbin/nvme"), \
            patch.object(wipeutils, "_command_json", return_value=identify):
        caps = wipeutils.nvme_secure_erase_capabilities("/dev/nvme0n1")

    assert caps == {
        "format": True,
        "crypto": True,
        "format_all_namespaces": True,
        "secure_erase_all_namespaces": True,
        "namespace_count": 2,
    }


def test_nvme_namespace_format_preserves_all_format_settings():
    identify = {"flbas": 0x11, "dps": 0x0a}
    with patch.object(wipeutils, "nvme_cli_path", return_value="/usr/sbin/nvme"), \
            patch.object(wipeutils, "_command_json", return_value=identify):
        namespace_format = wipeutils.nvme_namespace_format("/dev/nvme0n1")

    assert namespace_format == {
        "lbaf": 1,
        "ms": 1,
        "pi": 2,
        "pil": 1,
    }


def test_nvme_secure_erase_prefers_crypto_and_keeps_lba_format():
    caps = {
        "format": True,
        "crypto": True,
        "format_all_namespaces": False,
        "secure_erase_all_namespaces": False,
        "namespace_count": 1,
    }
    with patch.object(raw_wipe, "nvme_secure_erase_capabilities",
                      return_value=caps), \
            patch.object(raw_wipe, "nvme_namespace_count", return_value=1), \
            patch.object(raw_wipe, "nvme_namespace_format", return_value={
                "lbaf": 2, "ms": 1, "pi": 3, "pil": 0
            }), \
            patch.object(raw_wipe, "nvme_cli_path",
                         return_value="/usr/sbin/nvme"), \
            patch.object(raw_wipe, "nvme_format_force_supported",
                         return_value=True), \
            patch.object(raw_wipe, "_execute_simple") as execute:
        raw_wipe._nvme_secure_erase("/dev/nvme0n1", "auto")

    execute.assert_called_once_with([
        "/usr/sbin/nvme", "format", "/dev/nvme0n1",
        "--lbaf=2", "--ms=1", "--pi=3", "--pil=0", "--ses=2", "--force"
    ])


def test_nvme_secure_erase_fails_closed_when_namespace_scope_is_unknown():
    caps = {
        "format": True,
        "crypto": False,
        "format_all_namespaces": True,
        "secure_erase_all_namespaces": False,
        "namespace_count": 2,
    }
    with patch.object(raw_wipe, "nvme_secure_erase_capabilities",
                      return_value=caps), \
            patch.object(raw_wipe, "nvme_namespace_count", return_value=0), \
            patch.object(raw_wipe, "_execute_simple") as execute:
        with pytest.raises(wipeutils.EraseNotSupported):
            raw_wipe._nvme_secure_erase("/dev/nvme0n1", "user")

    execute.assert_not_called()


def test_discard_unmounts_then_uses_blkdiscard_without_dd():
    with patch.object(raw_wipe, "is_block_device", return_value=True), \
            patch.object(raw_wipe.shutil, "which", return_value="/bin/umount"), \
            patch.object(raw_wipe, "do_umount") as unmount, \
            patch.object(raw_wipe, "command_path",
                         return_value="/sbin/blkdiscard"), \
            patch.object(raw_wipe, "_execute_simple") as execute, \
            patch.object(raw_wipe, "execute") as dd_execute:
        raw_wipe.raw_wipe(
            "/dev/sda", 1, "zero", False, None, "1M", method="discard")

    unmount.assert_called_once_with("/dev/sda")
    execute.assert_called_once_with(["/sbin/blkdiscard", "/dev/sda"])
    dd_execute.assert_not_called()


def test_controller_secure_erase_uses_ata_enhanced_when_needed():
    caps = {"secure": False, "enhanced": True, "frozen": False}
    with patch.object(raw_wipe, "is_nvme_namespace", return_value=False), \
            patch.object(raw_wipe, "_find_udisks_drive_ata",
                         return_value=object()), \
            patch.object(raw_wipe, "ata_security_capabilities",
                         return_value=caps), \
            patch.object(raw_wipe, "_ata_secure_erase") as ata_erase, \
            patch.object(raw_wipe, "supports_discard", return_value=False):
        raw_wipe._controller_secure_erase("/dev/sda")

    ata_erase.assert_called_once_with("/dev/sda", enhanced=True)


def test_ata_security_capabilities_respect_frozen_state():
    class FakeAta(object):
        values = {
            "security-erase-unit-minutes": 2,
            "security-enhanced-erase-unit-minutes": 3,
            "security-frozen": True,
        }

        def get_property(self, name):
            return self.values[name]

    assert wipeutils.ata_security_capabilities(FakeAta()) == {
        "secure": True, "enhanced": True, "frozen": True
    }
