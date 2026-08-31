import glob
import json
import os
import re
import shutil
from subprocess import PIPE, Popen


_NVME_NAMESPACE_RE = re.compile(r"^(nvme[0-9]+)n[0-9]+$")


class EraseNotSupported(RuntimeError):
    """Raised when a requested controller erase method is unavailable."""


def _read_int(path):
    try:
        with open(path, "r") as handle:
            return int(handle.read().strip(), 0)
    except (IOError, OSError, ValueError):
        return None


def _as_int(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return None
    return None


def block_name(device):
    return os.path.basename(os.path.realpath(device))


def is_nvme_namespace(device):
    return _NVME_NAMESPACE_RE.match(block_name(device)) is not None


def nvme_controller_path(device):
    match = _NVME_NAMESPACE_RE.match(block_name(device))
    if match is None:
        return None
    return "/dev/{}".format(match.group(1))


def supports_discard(device):
    value = _read_int("/sys/class/block/{}/queue/discard_max_bytes".format(
        block_name(device)))
    return value is not None and value > 0


def command_path(name):
    path = shutil.which(name)
    if path:
        return path
    for directory in ("/usr/sbin", "/usr/bin", "/sbin", "/bin"):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def nvme_cli_path():
    return command_path("nvme")


def nvme_cli_available():
    return nvme_cli_path() is not None


def nvme_format_force_supported():
    nvme = nvme_cli_path()
    if nvme is None:
        return False
    process = Popen([nvme, "format", "--help"], stdout=PIPE, stderr=PIPE,
                    universal_newlines=True)
    stdout, stderr = process.communicate()
    return "--force" in (stdout + stderr)


def _command_json(command):
    process = Popen(command, stdout=PIPE, stderr=PIPE,
                    universal_newlines=True)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        detail = stderr.strip() or stdout.strip() or "command failed"
        raise EraseNotSupported(detail)
    try:
        return json.loads(stdout)
    except (TypeError, ValueError):
        raise EraseNotSupported("NVMe identify output is not valid JSON")


def nvme_secure_erase_capabilities(device):
    controller = nvme_controller_path(device)
    if controller is None:
        raise EraseNotSupported("The target is not an NVMe namespace")
    nvme = nvme_cli_path()
    if nvme is None:
        raise EraseNotSupported("nvme-cli is not installed")

    data = _command_json([nvme, "id-ctrl", "-o", "json", controller])
    oacs = _as_int(data.get("oacs"))
    fna = _as_int(data.get("fna"))
    namespace_count = _as_int(data.get("nn"))
    if oacs is None or fna is None or namespace_count is None:
        raise EraseNotSupported("NVMe erase capabilities could not be read")

    return {
        "format": bool(oacs & 0x2),
        "crypto": bool(fna & 0x4),
        "format_all_namespaces": bool(fna & 0x1),
        "secure_erase_all_namespaces": bool(fna & 0x2),
        "namespace_count": namespace_count,
    }


def nvme_namespace_count(device):
    controller = nvme_controller_path(device)
    if controller is None:
        return 0
    controller_name = os.path.basename(controller)
    pattern = re.compile(r"^{}n[0-9]+$".format(re.escape(controller_name)))
    names = [os.path.basename(path)
             for path in glob.glob("/sys/class/block/{}n*".format(controller_name))]
    return sum(1 for name in names if pattern.match(name))


def nvme_namespace_format(device):
    nvme = nvme_cli_path()
    if nvme is None:
        raise EraseNotSupported("nvme-cli is not installed")
    data = _command_json([nvme, "id-ns", "-o", "json", device])
    flbas = _as_int(data.get("flbas"))
    dps = _as_int(data.get("dps"))
    if flbas is None or dps is None:
        raise EraseNotSupported(
            "The active NVMe namespace format could not be determined")
    if flbas & 0x60:
        raise EraseNotSupported(
            "Extended NVMe LBA format indexes are not supported by this nvme-cli")
    return {
        "lbaf": flbas & 0x0f,
        "ms": (flbas >> 4) & 0x1,
        "pi": dps & 0x7,
        "pil": (dps >> 3) & 0x1,
    }


def ata_security_capabilities(drive_ata):
    result = {"secure": False, "enhanced": False, "frozen": False}
    if drive_ata is None:
        return result
    try:
        result["secure"] = int(drive_ata.get_property(
            "security-erase-unit-minutes")) > 0
        result["enhanced"] = int(drive_ata.get_property(
            "security-enhanced-erase-unit-minutes")) > 0
        result["frozen"] = bool(drive_ata.get_property("security-frozen"))
    except (AttributeError, TypeError, ValueError):
        pass
    return result
