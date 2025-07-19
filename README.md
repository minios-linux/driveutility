# Drive Utility

## Overview

Drive Utility is a GTK3-based graphical utility designed for comprehensive management of disk devices on Linux systems. It provides a user-friendly interface for common disk operations, including writing disk images to drives, formatting disks with various filesystems, and securely wiping data.

Built with Python 3, Drive Utility leverages `UDisks2` for robust device detection and integrates with `pkexec` to securely handle operations requiring elevated privileges, ensuring a smooth and safe user experience.

## Features

*   **Image Writing:** Easily burn `.iso`, `.img`, or `.bin` files to USB drives, SD cards, or other removable media.
*   **Disk Formatting:** Format entire disk devices with popular filesystems such as FAT32, exFAT, NTFS, and EXT4. Users can specify a custom volume label for the new partition.
*   **Secure Disk Wiping:** Erase sensitive data from disks using various wiping methods, including:
    *   Zero fill (overwriting with zeros)
    *   Random data (overwriting with random patterns)
    *   Multiple passes (for enhanced data security)
    *   Option for a final zero-fill pass.