#!/usr/bin/python3

import argparse
import os
import queue
import stat
import subprocess
import sys
import threading
import syslog

# Add the shared library path
sys.path.append('/usr/lib/driveutility')
from mountutils import do_umount

WIPE_SOURCES = {
    'zero': '/dev/zero',
    'random': '/dev/urandom',
}

def reader_thread(pipe, q):
    """Reads lines from a pipe and puts them into a queue."""
    try:
        with pipe:
            for line in iter(pipe.readline, ''):
                sys.stderr.write(line)
                sys.stderr.flush()
                q.put(line)
    finally:
        q.put(None) # Signal that reading is complete

def execute(command):
    """
    Executes a command, showing its stderr in real-time while capturing it for analysis.
    This function correctly handles the 'No space left on device' case for 'dd'.
    """
    syslog.syslog("Executing: " + " ".join(command))
    
    process = subprocess.Popen(command, 
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.PIPE,
                               text=True, 
                               bufsize=1, 
                               universal_newlines=True)

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
            syslog.syslog(f"dd finished with an expected 'No space' message.")
        else:
            syslog.syslog(f"Command failed with exit code {return_code}: {' '.join(command)}")
            syslog.syslog(f"Stderr: {stderr_output.strip()}")
            print("\nfailed")
            sys.exit(1)

    subprocess.call(["sync"])

def raw_wipe(device, passes, wipe_type, final_zero, size_mb, block_size):
    """Overwrites a device with the specified pattern."""
    if wipe_type not in WIPE_SOURCES:
        syslog.syslog(f"Error: Invalid wipe type '{wipe_type}'")
        print("failed")
        sys.exit(1)

    syslog.syslog(f"Unmounting {device}")
    do_umount(device)

    count = size_mb if size_mb is not None else None
    source_path = WIPE_SOURCES[wipe_type]

    for i in range(1, passes + 1):
        print(f"\n--- Pass {i}/{passes}: Wiping with '{wipe_type}' ---")
        
        dd_command = [
            'dd', f'if={source_path}', f'of={device}',
            f'bs={block_size}', 'status=progress'
        ]
        if count is not None:
            dd_command.append(f'count={count}')
        
        execute(dd_command)

    if wipe_type == 'random' and final_zero:
        print("\n--- Final Pass: Wiping with 'zero' ---")
        
        dd_command = [
            'dd', f'if={WIPE_SOURCES["zero"]}', f'of={device}',
            f'bs={block_size}', 'status=progress'
        ]
        if count is not None:
            dd_command.append(f'count={count}')
            
        execute(dd_command)

    syslog.syslog(f"Wipe completed for {device}")

def main():
    try:
        parser = argparse.ArgumentParser(
            description="Securely wipe a storage device.",
            prog="driveutility-wipe",
            epilog="Example: driveutility-wipe -d /dev/sdb -p 3 -t random"
        )
        parser.add_argument('-d', '--device', help="Block device path to wipe (e.g., /dev/sdb)", type=str, required=True)
        parser.add_argument('-p', '--passes', help="Number of overwrite passes (default: 1)", type=int, default=1)
        parser.add_argument('-t', '--type', help="Wipe pattern: 'zero' or 'random' (default: 'zero')", type=str, choices=list(WIPE_SOURCES), default='zero')
        parser.add_argument('-z', '--final-zero', help="For random wipes, add a final zero-fill pass", action='store_true')
        parser.add_argument('-s', '--size', help="Size in MB to wipe (default: entire device)", type=int, default=None)
        parser.add_argument('-b', '--block-size', help="Block size for dd (default: 1M)", type=str, default='1M')
        args = parser.parse_args()
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(2)

    try:
        mode = os.stat(args.device).st_mode
        if not stat.S_ISBLK(mode):
            print(f"Error: The specified path '{args.device}' is not a block device.", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print(f"Error: The specified device '{args.device}' does not exist.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Could not access device '{args.device}': {e}", file=sys.stderr)
        sys.exit(1)

    try:
        raw_wipe(
            device=args.device,
            passes=args.passes,
            wipe_type=args.type,
            final_zero=args.final_zero,
            size_mb=args.size,
            block_size=args.block_size
        )
        print("\nsuccess")
        sys.exit(0)
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        syslog.syslog(f"An unexpected exception occurred during wipe: {str(e)}")
        print("failed", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()