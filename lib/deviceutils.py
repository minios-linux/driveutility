import os
import stat


def _as_text(value):
    """Return a UDisks byte/string property as a normal path string."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "surrogateescape")
    if value is None:
        return ""
    return str(value).rstrip("\0")


def is_block_device(path):
    """Return whether *path* names a block device below /dev."""
    if not isinstance(path, str) or not path.startswith("/dev/"):
        return False
    if ".." in path.split(os.sep):
        return False
    try:
        return stat.S_ISBLK(os.stat(path).st_mode)
    except (OSError, IOError):
        return False


def is_same_device_or_partition(source, target):
    """Match a target device and only its conventionally named partitions."""
    if not source or not target:
        return False

    source = os.path.realpath(source)
    target = os.path.realpath(target)
    if source == target:
        return True
    if os.path.dirname(source) != os.path.dirname(target):
        return False

    source_name = os.path.basename(source)
    target_name = os.path.basename(target)
    separator = "p" if target_name[-1:].isdigit() else ""
    prefix = target_name + separator
    if not source_name.startswith(prefix):
        return False
    partition_number = source_name[len(prefix):]
    return bool(partition_number) and partition_number.isdigit()


def _block_paths(block):
    paths = []
    device = _as_text(block.get_property("device"))
    if device:
        paths.append(device)
    try:
        symlinks = block.get_property("symlinks") or []
    except (TypeError, AttributeError):
        symlinks = []
    paths.extend(_as_text(path) for path in symlinks if _as_text(path))
    return paths


def _path_keys(path):
    if not path:
        return set()
    return {os.path.normpath(path), os.path.realpath(path)}


def resolve_udisks_disk_path(object_manager, requested_path):
    """Resolve an exact UDisks disk or partition path to its whole disk.

    Unknown, ambiguous, non-device, and orphaned partition paths fail closed.
    UDisks' partition-table relation is authoritative; device-name heuristics
    are deliberately not used here.
    """
    if (not isinstance(requested_path, str)
            or not requested_path.startswith("/dev/")
            or ".." in requested_path.split(os.sep)):
        return None

    requested_keys = _path_keys(requested_path)
    matches = []
    for obj in object_manager.get_objects():
        block = obj.get_block()
        if not block:
            continue
        if any(requested_keys.intersection(_path_keys(path))
               for path in _block_paths(block)):
            matches.append(obj)

    if len(matches) != 1:
        return None

    selected = matches[0]
    partition = selected.get_partition()
    if partition:
        table_path = _as_text(partition.get_property("table"))
        if not table_path or table_path == "/":
            return None
        selected = object_manager.get_object(table_path)
        if not selected:
            return None

    block = selected.get_block()
    if not block:
        return None
    device = _as_text(block.get_property("device"))
    return device or None
