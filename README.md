# Drive Utility

## Overview


Drive Utility is a GTK3-based graphical utility for comprehensive management of disk devices on Linux systems. The intuitive interface allows you to:

* **Write images** to USB drives, SD cards, and other devices from `.iso`, `.img`, or other supported files, making bootable media or restoring backups.
* **Create images** from physical devices ("read" mode), including on-the-fly compression (gzip, bzip2, xz, lz4, zstd) and assignment of file ownership to the current user for easy access.
* **Format disks** with popular filesystems (FAT32, exFAT, NTFS, EXT4), with the ability to set a custom volume label and specify user/group ownership for ext4.
* **Securely wipe disks** using zeros or random data, with support for multiple passes and an optional final zero-fill for maximum data destruction.

Key features:
- Automatic detection and display of all connected storage devices, with clear size and model information.
- No need to manually unmount devices: all operations handle this automatically.
- Progress bars and detailed status for all operations.
- Built-in safety: integrates with PolicyKit and `pkexec` to request privileges only when needed, minimizing risk.
- All actions are localized and support multiple languages.

Drive Utility is built with Python 3 and leverages `UDisks2` for robust device management. It is suitable for both beginners and advanced users who need a reliable, safe, and user-friendly tool for disk operations.

<div align="center">
  <img width="480" height="295" alt="Writer" src="https://github.com/user-attachments/assets/b4ab1424-94d7-4469-9c6a-f49d75d96ed3" /></br>
  <img width="480" height="295" alt="Formatter" src="https://github.com/user-attachments/assets/ffcb5d0a-dd5d-4569-a70d-219898bc449a" /></br>
  <img width="480" height="295" alt="Wiper" src="https://github.com/user-attachments/assets/23ad8ea6-bf37-4af3-97bc-7314fbc1496d" /></br>
</div>

## Features

*   **Image Writing:** Easily burn `.iso`, `.img`, or `.bin` files to USB drives, SD cards, or other removable media.
*   **Disk Formatting:** Format entire disk devices with popular filesystems such as FAT32, exFAT, NTFS, and EXT4. Users can specify a custom volume label for the new partition.
*   **Secure Disk Wiping:** Erase sensitive data from disks using various wiping methods, including:
    *   Zero fill (overwriting with zeros)
    *   Random data (overwriting with random patterns)
    *   Multiple passes (for enhanced data security)
    *   Option for a final zero-fill pass.

## Command-line utilities

Drive Utility also provides a set of powerful command-line tools for scripting and advanced usage:

### driveutility-write
Write a disk image or device to a target device (raw copy).

Example:
```sh
sudo driveutility-write -s /path/to/image.iso -t /dev/sdX
```

### driveutility-read
Create an image from a device, with optional compression.

Example:
```sh
sudo driveutility-read -s /dev/sdX -t /path/to/backup.img -c gzip
```

### driveutility-format
Format a device with a specified filesystem and set ownership.

Example:
```sh
sudo driveutility-format -d /dev/sdX -f ext4 -u 1000 -g 1000 "MYDISK"
```

### driveutility-wipe
Securely wipe a device with zeros or random data, with multiple passes.

Example:
```sh
sudo driveutility-wipe -d /dev/sdX -p 3 -t random -z
```

See the man pages (`man driveutility-write`, etc.) for full details and options.
