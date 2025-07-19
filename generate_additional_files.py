#!/usr/bin/python3

DOMAIN = "driveutility"
SYSTEM_LOCALE_PATH = "/usr/share/locale"
LOCAL_LOCALE_PATH = "mo"

import os
import gettext

# --- Determine the correct path for translations (local first) ---
if os.path.isdir(LOCAL_LOCALE_PATH):
    LOCALE_PATH = LOCAL_LOCALE_PATH
    print(f"Using local translations from: {LOCALE_PATH}")
elif os.path.isdir(SYSTEM_LOCALE_PATH):
    LOCALE_PATH = SYSTEM_LOCALE_PATH
    print(f"Using system translations from: {LOCALE_PATH}")
else:
    LOCALE_PATH = None
    print("Warning: No translation directory found. Only default strings will be used.")

# Set the default language to get the base strings
os.environ['LANGUAGE'] = "en_US.UTF-8"
if LOCALE_PATH:
    gettext.install(DOMAIN, LOCALE_PATH)
else:
    gettext.install(DOMAIN)


# --- Helper Functions ---

def strip_split_and_recombine(comma_separated):
    """Converts a comma-separated string like 'a, b, c' to 'a;b;c;' for the Keywords field."""
    word_list = comma_separated.split(",")
    out = ""
    for item in word_list:
        out += item.strip()
        out += ";"
    return out

def generate(domain, locale_path, filename, prefix, name, comment, suffix, genericName=None, keywords=None, append=False):
    """Generates a .desktop file with support for translations."""
    directory_path = os.path.dirname(filename)
    if directory_path:
        os.makedirs(directory_path, exist_ok=True)

    mode = "a" if append else "w"
    with open(filename, mode, encoding="utf-8") as desktopFile:
        desktopFile.writelines(prefix)

        translatable_fields = {
            "Name": name,
            "Comment": comment,
            "GenericName": genericName,
            "Keywords": keywords
        }

        for key, value in translatable_fields.items():
            if value is None:
                continue

            formatted_value = strip_split_and_recombine(value) if key == "Keywords" else value
            desktopFile.write(f"{key}={formatted_value}\n")

            if locale_path:
                for directory in sorted(os.listdir(locale_path)):
                    mo_file = os.path.join(locale_path, directory, "LC_MESSAGES", f"{domain}.mo")
                    if os.path.exists(mo_file):
                        try:
                            language = gettext.translation(domain, locale_path, languages=[directory])
                            L_ = language.gettext
                            translated_value = L_(value)
                            if translated_value != value:
                                formatted_translated = strip_split_and_recombine(translated_value) if key == "Keywords" else translated_value
                                desktopFile.write(f"{key}[{directory}]={formatted_translated}\n")
                        except Exception:
                            pass

        desktopFile.writelines(suffix)

def generate_polkit_policy(domain, locale_path, filename, prefix, description, message, suffix):
    """Generates a .policy file with support for translations."""
    directory_path = os.path.dirname(filename)
    if directory_path:
        os.makedirs(directory_path, exist_ok=True)

    with open(filename, "w", encoding="utf-8") as policyFile:
        policyFile.writelines(prefix)

        fields_to_translate = {
            "description": description,
            "message": message
        }

        for tag, text in fields_to_translate.items():
            policyFile.write(f"<{tag}>{text}</{tag}>\n")
            if locale_path:
                for directory in sorted(os.listdir(locale_path)):
                    mo_file = os.path.join(locale_path, directory, "LC_MESSAGES", f"{domain}.mo")
                    if os.path.exists(mo_file):
                        try:
                            language = gettext.translation(domain, locale_path, languages=[directory])
                            L_ = language.gettext
                            translated_value = L_(text)
                            if translated_value != text:
                                translated_value = translated_value.replace("&", "&").replace("<", "<").replace(">", ">")
                                policyFile.write(f'<{tag} xml:lang="{directory}">{translated_value}</{tag}>\n')
                        except Exception:
                            pass

        policyFile.writelines(suffix)


# --- 1. Create main .desktop file for application menu (System category) ---

# Main .desktop file for GNOME/GTK environments.
main_prefix = """[Desktop Entry]
Type=Application
Exec=driveutility
Icon=driveutility
Terminal=false
Categories=GTK;System;
NotShowIn=KDE;
"""
keywords = "usb,iso,image,write,flash,bootable,format,fat32,ntfs,ext4,erase,wipe,disk"
generate(DOMAIN, LOCALE_PATH, "share/applications/driveutility.desktop",
         main_prefix,
         _("Drive Utility"),
         _("Write disk images, format, or wipe drives"),
         "",
         genericName=_("Drive Management"),
         keywords=_(keywords))

# Optional .desktop file for KDE.
kde_prefix = """[Desktop Entry]
Type=Application
Exec=driveutility
Icon=driveutility
Terminal=false
Categories=System;
OnlyShowIn=KDE;
"""
generate(DOMAIN, LOCALE_PATH, "share/applications/driveutility-kde.desktop",
         kde_prefix,
         _("Drive Utility"),
         _("Write disk images, format, or wipe drives"),
         "",
         genericName=_("Drive Management"),
         keywords=_(keywords))


# --- 2. Create .desktop files for individual actions (Utility category) ---

# --- Write Action ---
write_prefix_gtk = """[Desktop Entry]
Type=Application
Exec=driveutility -m write
Icon=driveutility
Terminal=false
Categories=GTK;Utility;
NotShowIn=KDE;
"""
generate(DOMAIN, LOCALE_PATH, "share/applications/driveutility-writer.desktop",
         write_prefix_gtk,
         _("Image writer"),
         _("Write a disk image to a device"),
         "")

write_prefix_kde = """[Desktop Entry]
Type=Application
Exec=driveutility -m write
Icon=driveutility
Terminal=false
Categories=Utility;
OnlyShowIn=KDE;
"""
generate(DOMAIN, LOCALE_PATH, "share/applications/driveutility-writer-kde.desktop",
         write_prefix_kde,
         _("Image writer"),
         _("Write a disk image to a device"),
         "")

# --- Format Action ---
format_prefix_gtk = """[Desktop Entry]
Type=Application
Exec=driveutility -m format
Icon=driveutility
Terminal=false
Categories=GTK;Utility;
NotShowIn=KDE;
"""
generate(DOMAIN, LOCALE_PATH, "share/applications/driveutility-formatter.desktop",
         format_prefix_gtk,
         _("Disk formatter"),
         _("Format a disk"),
         "")

format_prefix_kde = """[Desktop Entry]
Type=Application
Exec=driveutility -m format
Icon=driveutility
Terminal=false
Categories=Utility;
OnlyShowIn=KDE;
"""
generate(DOMAIN, LOCALE_PATH, "share/applications/driveutility-formatter-kde.desktop",
         format_prefix_kde,
         _("Disk formatter"),
         _("Format a disk"),
         "")

# --- Wipe Action ---
wipe_prefix_gtk = """[Desktop Entry]
Type=Application
Exec=driveutility -m wipe
Icon=driveutility
Terminal=false
Categories=GTK;Utility;
NotShowIn=KDE;
"""
generate(DOMAIN, LOCALE_PATH, "share/applications/driveutility-wiper.desktop",
         wipe_prefix_gtk,
         _("Disk wiper"),
         _("Wipe a disk"),
         "")

wipe_prefix_kde = """[Desktop Entry]
Type=Application
Exec=driveutility -m wipe
Icon=driveutility
Terminal=false
Categories=Utility;
OnlyShowIn=KDE;
"""
generate(DOMAIN, LOCALE_PATH, "share/applications/driveutility-wiper-kde.desktop",
         wipe_prefix_kde,
         _("Disk wiper"),
         _("Wipe a disk"),
         "")


# --- 3. Create actions for file managers (Nemo) ---

# Action for Nemo (writing an image)
nemo_write_prefix = """[Nemo Action]
Active=true
Name[C]=Write image...
Comment[C]=Write this image file to a device
Exec=driveutility -m write -i %F
Icon-Name=driveutility
Selection=S
Extensions=iso;img;bin;raw;dd;
"""
generate(DOMAIN, LOCALE_PATH, "share/nemo/actions/driveutility-writer.nemo_action",
         nemo_write_prefix,
         _("Write image..."),
         _("Write this image file to a device"),
         "")

# Action for Nemo (formatting)
nemo_format_prefix = """[Nemo Action]
Active=true
Name[C]=Format...
Comment[C]=Format this device
Exec=driveutility -m format -d %F
Icon-Name=driveutility
Selection=S
Extensions=dir;
Mimetypes=inode/directory;
Dependencies=udisks2;
"""
generate(DOMAIN, LOCALE_PATH, "share/nemo/actions/driveutility-formatter.nemo_action",
         nemo_format_prefix,
         _("Format..."),
         _("Format this device"),
         "")

# Action for Nemo (wiping)
nemo_wipe_prefix = """[Nemo Action]
Active=true
Name[C]=Wipe...
Comment[C]=Wipe this device
Exec=driveutility -m wipe -d %F
Icon-Name=driveutility
Selection=S
Extensions=dir;
Mimetypes=inode/directory;
Dependencies=udisks2;
"""
generate(DOMAIN, LOCALE_PATH, "share/nemo/actions/driveutility-wiper.nemo_action",
         nemo_wipe_prefix,
         _("Wipe..."),
         _("Wipe this device"),
         "")


# --- 4. Create PolicyKit rules ---

polkit_suffix = """
    <defaults>
      <allow_any>no</allow_any>
      <allow_inactive>no</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
"""

# Rule for writing an image
polkit_write_prefix = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">
<policyconfig>
  <vendor>MiniOS</vendor>
  <vendor_url>https://minios.dev</vendor_url>
  <action id="dev.minios.driveutility-write">
    <icon_name>driveutility</icon_name>
"""
polkit_write_suffix = f"""
    <annotate key="org.freedesktop.policykit.exec.path">/usr/bin/driveutility-write</annotate>
{polkit_suffix}
"""
generate_polkit_policy(DOMAIN, LOCALE_PATH, "share/polkit/actions/dev.minios.driveutility-write.policy",
                       polkit_write_prefix,
                       _("Write a disk image"),
                       _("Authentication is required to write an image to a device."),
                       polkit_write_suffix)

# Rule for formatting
polkit_format_prefix = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">
<policyconfig>
  <vendor>MiniOS</vendor>
  <vendor_url>https://minios.dev</vendor_url>
  <action id="dev.minios.driveutility-format">
    <icon_name>driveutility</icon_name>
"""
polkit_format_suffix = f"""
    <annotate key="org.freedesktop.policykit.exec.path">/usr/bin/driveutility-format</annotate>
{polkit_suffix}
"""
generate_polkit_policy(DOMAIN, LOCALE_PATH, "share/polkit/actions/dev.minios.driveutility-format.policy",
                       polkit_format_prefix,
                       _("Format a disk"),
                       _("Authentication is required to format a device."),
                       polkit_format_suffix)

# Rule for wiping
polkit_wipe_prefix = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE policyconfig PUBLIC
 \"-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN\"
 \"http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd\">
<policyconfig>
  <vendor>MiniOS</vendor>
  <vendor_url>https://minios.dev</vendor_url>
  <action id=\"dev.minios.driveutility-wipe\">
    <icon_name>driveutility</icon_name>
"""
polkit_wipe_suffix = f"""
    <annotate key=\"org.freedesktop.policykit.exec.path\">/usr/bin/driveutility-wipe</annotate>
{polkit_suffix}
"""
generate_polkit_policy(DOMAIN, LOCALE_PATH, "share/polkit/actions/dev.minios.driveutility-wipe.policy",
                       polkit_wipe_prefix,
                       _("Wipe a disk"),
                       _("Authentication is required to wipe a device."),
                       polkit_wipe_suffix)

print("Generated all files successfully.")