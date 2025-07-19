# Drive Utility

<div align="center">
  <img width="480" height="295" alt="1" src="https://github.com/user-attachments/assets/9912f6ab-d1f0-4dcd-8200-88a0962c6c38" /></br>
  <img width="480" height="295" alt="2" src="https://github.com/user-attachments/assets/93118c13-c26f-4412-9f09-cde1c105bc67" /></br>
  <img width="480" height="295" alt="3" src="https://github.com/user-attachments/assets/44fd86d7-7c3a-4d21-8266-8d39dc45a7e9" /></br>
</div>

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
