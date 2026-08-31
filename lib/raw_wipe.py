#!/usr/bin/python3

import argparse
import os
import queue
import shutil
from subprocess import DEVNULL, PIPE, Popen, call
import sys
import threading
import syslog

# Add the shared library path
sys.path.append('/usr/lib/driveutility')
from deviceutils import is_block_device
from mountutils import do_umount
from wipeutils import (
    EraseNotSupported,
    ata_security_capabilities,
    command_path,
    is_nvme_namespace,
    nvme_cli_path,
    nvme_format_force_supported,
    nvme_namespace_count,
    nvme_namespace_format,
    nvme_secure_erase_capabilities,
    supports_discard,
)

WIPE_SOURCES = {
    'zero': '/dev/zero',
    'random': '/dev/urandom',
}

ERASE_METHODS = (
    'zero', 'random', 'discard', 'secure', 'secure-discard',
    'nvme-user', 'nvme-crypto', 'ata-secure', 'ata-enhanced',
)


def reader_thread(pipe, q):
    """Reads lines from a pipe and puts them into a queue."""
    try:
        with pipe:
            for line in iter(pipe.readline, ''):
                sys.stderr.write(line)
                sys.stderr.flush()
                q.put(line)
    finally:
        q.put(None)  # Signal that reading is complete


def execute(command):
    """Execute dd, showing stderr and accepting its expected end-of-device."""
    syslog.syslog("Executing: " + " ".join(command))

    process = Popen(command,
                    stdout=DEVNULL,
                    stderr=PIPE,
                    universal_newlines=True,
                    bufsize=1)

    q = queue.Queue()
    thread = threading.Thread(target=reader_thread, args=[process.stderr, q])
    thread.daemon = True
    thread.start()

    return_code = process.wait()
    thread.join()

    stderr_lines = []
    while not q.empty():
        line = q.get_nowait()
        if line is None:
            continue
        stderr_lines.append(line)

    stderr_output = "".join(stderr_lines)

    if return_code != 0:
        if "No space left on device" in stderr_output:
            syslog.syslog("dd finished with an expected 'No space' message.")
        else:
            syslog.syslog("Command failed with exit code {}: {}".format(
                return_code, " ".join(command)))
            syslog.syslog("Stderr: {}".format(stderr_output.strip()))
            print("\nfailed")
            sys.exit(1)

    if call(["sync"]) != 0:
        syslog.syslog("sync failed after wipe command")
        sys.exit(1)


def _preflight_tools():
    missing = [tool for tool in ("dd", "sync", "umount")
               if shutil.which(tool) is None]
    if missing:
        raise RuntimeError("Missing required command(s): {}".format(
            ", ".join(missing)))


def _execute_simple(command):
    """Run a destructive helper and surface its error without a shell."""
    syslog.syslog("Executing: " + " ".join(command))
    process = Popen(command, stdout=PIPE, stderr=PIPE,
                    universal_newlines=True)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        detail = stderr.strip() or stdout.strip() or "command failed"
        raise EraseNotSupported(detail)
    if call(["sync"]) != 0:
        raise RuntimeError("sync failed after erase command")


def _find_udisks_drive_ata(device):
    try:
        import gi
        gi.require_version('UDisks', '2.0')
        from gi.repository import UDisks
    except (ImportError, ValueError) as error:
        raise EraseNotSupported("UDisks2 is unavailable: {}".format(error))

    client = UDisks.Client.new_sync()
    manager = client.get_object_manager()
    target = os.path.realpath(device)
    for obj in manager.get_objects():
        block = obj.get_block()
        if not block:
            continue
        block_device = block.get_property('device')
        if not block_device:
            continue
        if os.path.realpath(str(block_device)) != target:
            continue
        drive_path = block.get_property('drive')
        drive_obj = manager.get_object(drive_path) if drive_path else None
        return drive_obj.get_drive_ata() if drive_obj else None
    return None


def _ata_secure_erase(device, enhanced=False):
    try:
        import gi
        gi.require_version('GLib', '2.0')
        from gi.repository import GLib
    except (ImportError, ValueError) as error:
        raise EraseNotSupported("GLib is unavailable: {}".format(error))

    drive_ata = _find_udisks_drive_ata(device)
    capabilities = ata_security_capabilities(drive_ata)
    if capabilities['frozen']:
        raise EraseNotSupported("ATA security is frozen for this drive")
    key = 'enhanced' if enhanced else 'secure'
    if not capabilities[key]:
        raise EraseNotSupported("Requested ATA secure erase is not supported")

    options = GLib.Variant('a{sv}', {
        'enhanced': GLib.Variant('b', bool(enhanced)),
    })
    drive_ata.call_security_erase_unit_sync(options, None)


def _nvme_secure_erase(device, erase_type='auto'):
    capabilities = nvme_secure_erase_capabilities(device)
    if not capabilities['format']:
        raise EraseNotSupported("NVMe Format NVM is not supported")

    visible_namespace_count = nvme_namespace_count(device)
    applies_to_all = (capabilities['format_all_namespaces']
                      or capabilities['secure_erase_all_namespaces'])
    if (applies_to_all
            and (capabilities['namespace_count'] != 1
                 or visible_namespace_count != 1)):
        raise EraseNotSupported(
            "Secure erase could affect other namespaces on this NVMe controller")

    if erase_type == 'crypto':
        if not capabilities['crypto']:
            raise EraseNotSupported("NVMe cryptographic erase is not supported")
        ses = 2
    elif erase_type == 'user':
        ses = 1
    else:
        ses = 2 if capabilities['crypto'] else 1

    namespace_format = nvme_namespace_format(device)
    nvme = nvme_cli_path()
    if nvme is None:
        raise EraseNotSupported("nvme-cli is not installed")
    command = [
        nvme, 'format', device,
        '--lbaf={}'.format(namespace_format['lbaf']),
        '--ms={}'.format(namespace_format['ms']),
        '--pi={}'.format(namespace_format['pi']),
        '--pil={}'.format(namespace_format['pil']),
        '--ses={}'.format(ses),
    ]
    if nvme_format_force_supported():
        command.append('--force')
    _execute_simple(command)


def _controller_secure_erase(device):
    if is_nvme_namespace(device):
        _nvme_secure_erase(device, 'auto')
        return

    drive_ata = _find_udisks_drive_ata(device)
    capabilities = ata_security_capabilities(drive_ata)
    if not capabilities['frozen']:
        if capabilities['secure']:
            _ata_secure_erase(device, enhanced=False)
            return
        if capabilities['enhanced']:
            _ata_secure_erase(device, enhanced=True)
            return

    if supports_discard(device):
        blkdiscard = command_path('blkdiscard')
        if blkdiscard is None:
            raise EraseNotSupported("blkdiscard is not installed")
        _execute_simple([blkdiscard, '--secure', device])
        return
    raise EraseNotSupported("No controller secure erase method is available")


def raw_wipe(device, passes, wipe_type, final_zero, size_mb, block_size,
             method=None):
    """Erase a device using controller methods or host-side overwrite."""
    if not is_block_device(device):
        raise ValueError("The wipe target must be a block device")

    method = method or wipe_type
    if method not in ERASE_METHODS:
        raise ValueError("Invalid erase method '{}'".format(method))

    overwrite = method in WIPE_SOURCES
    if overwrite:
        if passes < 1:
            raise ValueError("Wipe passes must be at least 1")
        if size_mb is not None and size_mb <= 0:
            raise ValueError("Explicit wipe size must be greater than zero")
        _preflight_tools()
    elif shutil.which('umount') is None:
        raise RuntimeError("Missing required command: umount")

    syslog.syslog("Unmounting {}".format(device))
    do_umount(device)

    if method == 'discard':
        blkdiscard = command_path('blkdiscard')
        if blkdiscard is None:
            raise EraseNotSupported("blkdiscard is not installed")
        _execute_simple([blkdiscard, device])
        return
    if method == 'secure-discard':
        blkdiscard = command_path('blkdiscard')
        if blkdiscard is None:
            raise EraseNotSupported("blkdiscard is not installed")
        _execute_simple([blkdiscard, '--secure', device])
        return
    if method == 'secure':
        _controller_secure_erase(device)
        return
    if method == 'nvme-user':
        _nvme_secure_erase(device, 'user')
        return
    if method == 'nvme-crypto':
        _nvme_secure_erase(device, 'crypto')
        return
    if method == 'ata-secure':
        _ata_secure_erase(device, enhanced=False)
        return
    if method == 'ata-enhanced':
        _ata_secure_erase(device, enhanced=True)
        return

    count = size_mb if size_mb is not None else None
    source_path = WIPE_SOURCES[method]

    for i in range(1, passes + 1):
        print("\n--- Pass {}/{}: Wiping with '{}' ---".format(
            i, passes, method))

        dd_command = [
            'dd', 'if={}'.format(source_path), 'of={}'.format(device),
            'bs={}'.format(block_size), 'status=progress'
        ]
        if count is not None:
            dd_command.append('count={}'.format(count))

        execute(dd_command)

    if method == 'random' and final_zero:
        print("\n--- Final Pass: Wiping with 'zero' ---")

        dd_command = [
            'dd', 'if={}'.format(WIPE_SOURCES["zero"]),
            'of={}'.format(device), 'bs={}'.format(block_size),
            'status=progress'
        ]
        if count is not None:
            dd_command.append('count={}'.format(count))

        execute(dd_command)

    syslog.syslog("Wipe completed for {}".format(device))


def main():
    try:
        parser = argparse.ArgumentParser(
            description="Securely erase a storage device.",
            prog="driveutility-wipe",
            epilog="Example: driveutility-wipe -d /dev/sdb -m secure"
        )
        parser.add_argument('-d', '--device',
                            help="Block device path to erase (e.g., /dev/sdb)",
                            type=str, required=True)
        parser.add_argument('-p', '--passes',
                            help="Number of overwrite passes (default: 1)",
                            type=int, default=1)
        parser.add_argument('-t', '--type',
                            help="Legacy overwrite pattern: zero or random",
                            type=str, choices=list(WIPE_SOURCES), default='zero')
        parser.add_argument('-m', '--method',
                            help="Erase method (overrides --type)",
                            choices=list(ERASE_METHODS), default=None)
        parser.add_argument('-z', '--final-zero',
                            help="For random overwrites, add a final zero pass",
                            action='store_true')
        parser.add_argument('-s', '--size',
                            help="MB to overwrite (overwrite methods only)",
                            type=int, default=None)
        parser.add_argument('-b', '--block-size',
                            help="dd block size (default: 1M)",
                            type=str, default='1M')
        args = parser.parse_args()
    except Exception as error:
        print(error, file=sys.stderr)
        sys.exit(2)

    try:
        if not is_block_device(args.device):
            print("Error: The specified path '{}' is not a block device.".format(
                args.device), file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print("Error: The specified device '{}' does not exist.".format(
            args.device), file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("Error: Could not access device '{}': {}".format(
            args.device, error), file=sys.stderr)
        sys.exit(1)

    method = args.method or args.type
    if method in WIPE_SOURCES:
        if args.passes < 1:
            parser.error("passes must be at least 1")
        if args.size is not None and args.size <= 0:
            parser.error("size must be greater than zero when specified")

    try:
        raw_wipe(
            device=args.device,
            passes=args.passes,
            wipe_type=args.type,
            final_zero=args.final_zero,
            size_mb=args.size,
            block_size=args.block_size,
            method=args.method
        )
        print("\nsuccess")
        sys.exit(0)
    except SystemExit as error:
        sys.exit(error.code)
    except EraseNotSupported as error:
        syslog.syslog("Erase method unavailable: {}".format(str(error)))
        print("Unsupported erase method: {}".format(str(error)), file=sys.stderr)
        sys.exit(4)
    except Exception as error:
        syslog.syslog("An unexpected exception occurred during wipe: {}".format(
            str(error)))
        print("failed", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
