# Drive Utility

## Overview

Drive Utility is a GTK3-based graphical utility designed for comprehensive management of disk devices on Linux systems. It provides a user-friendly interface for common disk operations, including writing disk images to drives, formatting disks with various filesystems, and securely wiping data.

Built with Python 3, Drive Utility leverages `UDisks2` for robust device detection and integrates with `pkexec` to securely handle operations requiring elevated privileges, ensuring a smooth and safe user experience.

<div align="center">
  <img width="480" height="295" alt="Writer" src="https://github.com/user-attachments/assets/b4ab1424-94d7-4469-9c6a-f49d75d96ed3" /></br>
  <img width="480" height="295" alt="Formatter" src="https://github.com/user-attachments/assets/ffcb5d0a-dd5d-4569-a70d-219898bc449a" /></br>
  <img width="480" height="295" alt="3" src="https://github.com/user-attachments/assets/23ad8ea6-bf37-4af3-97bc-7314fbc1496d" /></br>
</div>

## Features

*   **Image Writing:** Easily burn `.iso`, `.img`, or `.bin` files to USB drives, SD cards, or other removable media.
*   **Disk Formatting:** Format entire disk devices with popular filesystems such as FAT32, exFAT, NTFS, and EXT4. Users can specify a custom volume label for the new partition.
*   **Secure Disk Wiping:** Erase sensitive data from disks using various wiping methods, including:
    *   Zero fill (overwriting with zeros)
    *   Random data (overwriting with random patterns)
    *   Multiple passes (for enhanced data security)
    *   Option for a final zero-fill pass.
