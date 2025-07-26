#!/usr/bin/python3

from unidecode import unidecode
from subprocess import Popen, PIPE
import getopt
import gettext
import gi
import locale
import os
import signal
import subprocess
import sys

gi.require_version('Polkit', '1.0')
gi.require_version('Gtk', '3.0')
gi.require_version('UDisks', '2.0')
gi.require_version('XApp', '1.0')

from gi.repository import Polkit, Gtk, GLib, UDisks, XApp

try:
    gi.require_version('Unity', '7.0')
    from gi.repository import Unity
    Using_Unity = True
except Exception:
    Using_Unity = False

if Using_Unity:
    launcher = Unity.LauncherEntry.get_for_desktop_id("driveutility.desktop")

APP = 'driveutility'
LOCALE_DIR = "/usr/share/locale"
locale.bindtextdomain(APP, LOCALE_DIR)
gettext.bindtextdomain(APP, LOCALE_DIR)
gettext.textdomain(APP)
_ = gettext.gettext

# https://technet.microsoft.com/en-us/library/bb490925.aspx
FORBIDDEN_CHARS = ["*", "?", "/", "\\", "|", ".", ",", ";", ":", "+", "=", "[", "]", "<", ">", "\""]

RELEVANT_UDISK_PROPERTIES = ['connection-bus', 'ejectable', 'id', \
'media-available', 'media-compatibility', 'media-removable', \
'model', 'vendor', 'optical', 'removable', 'size']

class DriveUtility:
    def __init__(self, image_path_arg=None, disk_path_arg=None, filesystem_arg=None, mode_arg=None, debug_arg=False):

        self.debug = debug_arg
        self.filesystem = filesystem_arg

        def devices_changed_callback(client):
            self.get_devices()

        self.udisks_client = UDisks.Client.new_sync()
        self.udisk_listener_id = self.udisks_client.connect("changed", devices_changed_callback)

        # --- UI Initialization ---
        self.wTree = Gtk.Builder()
        self.wTree.set_translation_domain(APP)
        self.wTree.add_from_file("/usr/share/driveutility/driveutility.ui")

        self.window = self.wTree.get_object("main_window")
        self.main_stack = self.wTree.get_object("main_stack")
        
        self.stack_switcher = self.wTree.get_object("stack_switcher")
        
        self.main_stack.connect("notify::visible-child", self.on_stack_child_changed)

        # --- Common attributes ---
        self.process = None
        self.source_id = None
        self.selected_write_device = None
        self.selected_read_device = None
        self.selected_format_device = None
        self.selected_wipe_device = None
        self.write_progress = None
        self.read_progress = None
        self.last_used_device_path = None

        # --- Write Mode Widgets ---
        self.write_device_combobox = self.wTree.get_object("write_device_combobox")
        self.write_button = self.wTree.get_object("write_button")
        self.write_progressbar = self.wTree.get_object("write_progressbar")
        self.write_file_chooser = self.wTree.get_object("write_filechooserbutton")
        self.show_all_disks_write_checkbutton = self.wTree.get_object("show_all_disks_write_checkbutton")
        self.write_combo_handler_id = None
        
        # --- Read (Create Image) Mode Widgets ---
        self.read_device_combobox = self.wTree.get_object("read_device_combobox")
        self.read_button = self.wTree.get_object("read_button")
        self.read_progressbar = self.wTree.get_object("read_progressbar")
        self.read_target_entry = self.wTree.get_object("read_target_entry")
        self.read_target_button = self.wTree.get_object("read_target_button")
        self.compression_combobox = self.wTree.get_object("compression_combobox")
        self.show_all_disks_read_checkbutton = self.wTree.get_object("show_all_disks_read_checkbutton")
        self.read_combo_handler_id = None

        # --- Format Mode Widgets ---
        self.format_device_combobox = self.wTree.get_object("format_device_combobox")
        self.format_button = self.wTree.get_object("format_button")
        self.label_entry = self.wTree.get_object("volume_label_entry")
        self.show_all_disks_format_checkbutton = self.wTree.get_object("show_all_disks_format_checkbutton")
        self.format_progressbar = self.wTree.get_object("format_progressbar")
        self.filesystem_combobox = self.wTree.get_object("filesystem_combobox")
        self.format_combo_handler_id = None
        
        # --- Wipe Mode Widgets ---
        self.wipe_device_combobox = self.wTree.get_object("wipe_device_combobox")
        self.wipe_button = self.wTree.get_object("wipe_button")
        self.wipe_progressbar = self.wTree.get_object("wipe_progressbar")
        self.wipe_type_combobox = self.wTree.get_object("wipe_type_combobox")
        self.wipe_passes_spinbutton = self.wTree.get_object("wipe_passes_spinbutton")
        self.wipe_size_spinbutton = self.wTree.get_object("wipe_size_spinbutton")
        self.wipe_final_zero_checkbutton = self.wTree.get_object("wipe_final_zero_checkbutton")
        self.show_all_disks_wipe_checkbutton = self.wTree.get_object("show_all_disks_wipe_checkbutton")
        self.wipe_combo_handler_id = None

        # --- Connect signals for synchronized checkboxes ---
        self.write_check_handler_id = self.show_all_disks_write_checkbutton.connect("toggled", self.on_checkbox_toggled)
        self.read_check_handler_id = self.show_all_disks_read_checkbutton.connect("toggled", self.on_checkbox_toggled)
        self.format_check_handler_id = self.show_all_disks_format_checkbutton.connect("toggled", self.on_checkbox_toggled)
        self.wipe_check_handler_id = self.show_all_disks_wipe_checkbutton.connect("toggled", self.on_checkbox_toggled)

        # --- Result Page Widgets and Connections ---
        self.wTree.get_object("write_result_back_button").connect("clicked", lambda w: self.go_back_to_main("write_page"))
        self.wTree.get_object("read_result_back_button").connect("clicked", lambda w: self.go_back_to_main("read_page"))
        self.wTree.get_object("format_result_back_button").connect("clicked", lambda w: self.go_back_to_main("format_page"))
        self.wTree.get_object("wipe_result_back_button").connect("clicked", lambda w: self.go_back_to_main("wipe_page"))
        self.wTree.get_object("windows_back_button").connect("clicked", lambda w: self.go_back_to_main("write_page"))

        # --- Models ---
        self.write_devicemodel = Gtk.ListStore(str, str)
        self.read_devicemodel = Gtk.ListStore(str, str)
        self.format_devicemodel = Gtk.ListStore(str, str)
        self.wipe_devicemodel = Gtk.ListStore(str, str)
        self.fsmodel = Gtk.ListStore(str, str, int, bool, bool)

        self.setup_write_mode()
        self.setup_read_mode()
        self.setup_format_mode()
        self.setup_wipe_mode()

        # --- Pre-fill widgets based on arguments ---
        if disk_path_arg:
            self.last_used_device_path = disk_path_arg
        
        self.get_devices()

        if image_path_arg and os.path.exists(image_path_arg):
            self.write_file_chooser.set_filename(image_path_arg)
            self.file_selected(self.write_file_chooser)

        if filesystem_arg:
            fs_iter = self.fsmodel.get_iter_first()
            while fs_iter:
                if self.fsmodel.get_value(fs_iter, 0) == filesystem_arg:
                    self.filesystem_combobox.set_active_iter(fs_iter)
                    break
                fs_iter = self.fsmodel.iter_next(fs_iter)

        # --- Set initial tab based on arguments ---
        if mode_arg == "write":
            self.main_stack.set_visible_child_name("write_page")
        elif mode_arg == "read":
            self.main_stack.set_visible_child_name("read_page")
        elif mode_arg == "format":
            self.main_stack.set_visible_child_name("format_page")
        elif mode_arg == "wipe":
            self.main_stack.set_visible_child_name("wipe_page")
        elif image_path_arg:
            self.main_stack.set_visible_child_name("write_page")
        elif disk_path_arg:
            self.main_stack.set_visible_child_name("format_page")

        self.window.connect("destroy", self.close)
        self.window.show()

    def on_stack_child_changed(self, stack, param):
        if self.process is not None:
            return

        new_page_name = stack.get_visible_child_name()
        if new_page_name in ("write_page", "read_page", "format_page", "wipe_page"):
            self.reset_ui_state()

    def reset_ui_state(self):
        self.set_write_sensitive(True)
        self.set_read_sensitive(True)
        self.set_format_sensitive(True)
        self.set_wipe_sensitive(True)
        self.clear_progress(self.write_progressbar)
        self.clear_progress(self.read_progressbar)
        self.clear_progress(self.format_progressbar)
        self.clear_progress(self.wipe_progressbar)

    def on_checkbox_toggled(self, widget):
        is_active = widget.get_active()

        self.show_all_disks_write_checkbutton.handler_block(self.write_check_handler_id)
        self.show_all_disks_read_checkbutton.handler_block(self.read_check_handler_id)
        self.show_all_disks_format_checkbutton.handler_block(self.format_check_handler_id)
        self.show_all_disks_wipe_checkbutton.handler_block(self.wipe_check_handler_id)

        self.show_all_disks_write_checkbutton.set_active(is_active)
        self.show_all_disks_read_checkbutton.set_active(is_active)
        self.show_all_disks_format_checkbutton.set_active(is_active)
        self.show_all_disks_wipe_checkbutton.set_active(is_active)

        self.show_all_disks_write_checkbutton.handler_unblock(self.write_check_handler_id)
        self.show_all_disks_read_checkbutton.handler_unblock(self.read_check_handler_id)
        self.show_all_disks_format_checkbutton.handler_unblock(self.format_check_handler_id)
        self.show_all_disks_wipe_checkbutton.handler_unblock(self.wipe_check_handler_id)

        self.get_devices()

    def go_back_to_main(self, page_name):
        self.main_stack.set_visible_child_name(page_name)

    def setup_write_mode(self):
        label = self.wTree.get_object("label_write_image")
        button = self.write_file_chooser.get_children()[0]
        label.set_mnemonic_widget(button)

        renderer_text = Gtk.CellRendererText()
        self.write_device_combobox.pack_start(renderer_text, True)
        self.write_device_combobox.add_attribute(renderer_text, "text", 1)
        self.write_device_combobox.set_model(self.write_devicemodel)

        filt = Gtk.FileFilter()
        filt.set_name(_("Disk Images"))
        filt.add_pattern("*.[iI][mM][gG]")
        filt.add_pattern("*.[iI][sS][oO]")
        filt.add_pattern("*.[bB][iI][nN]")
        filt.add_pattern("*.[gG][zZ]")
        filt.add_pattern("*.[bB][zZ]2")
        filt.add_pattern("*.[xX][zZ]")
        filt.add_pattern("*.[lL][zZ]4")
        filt.add_pattern("*.[zZ][sS][tT]")
        self.write_file_chooser.add_filter(filt)
        filt_all = Gtk.FileFilter()
        filt_all.set_name(_("All files"))
        filt_all.add_pattern("*")
        self.write_file_chooser.add_filter(filt_all)

        self.write_combo_handler_id = self.write_device_combobox.connect("changed", self.write_device_selected)
        self.write_button.connect("clicked", self.do_write)
        self.write_file_chooser.connect("file-set", self.file_selected)

    def setup_read_mode(self):
        renderer_text = Gtk.CellRendererText()
        self.read_device_combobox.pack_start(renderer_text, True)
        self.read_device_combobox.add_attribute(renderer_text, "text", 1)
        self.read_device_combobox.set_model(self.read_devicemodel)

        self.read_combo_handler_id = self.read_device_combobox.connect("changed", self.read_device_selected)
        self.read_button.connect("clicked", self.do_read)
        self.read_target_button.connect("clicked", self.on_read_target_button_clicked)
        self.read_target_entry.connect("changed", self.file_selected)

    def on_read_target_button_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            title=_("Save Image File"),
            parent=self.window,
            action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            self.read_target_entry.set_text(filename)
        
        dialog.destroy()

    def setup_format_mode(self):
        self.label_entry.set_text("")
        self.label_entry_changed_id = self.label_entry.connect("changed", self.on_label_entry_text_changed)

        self.format_button.connect("clicked", self.do_format)
        self.filesystem_combobox.connect("changed", self.filesystem_selected)
        self.format_combo_handler_id = self.format_device_combobox.connect("changed", self.format_device_selected)
        self.label_entry.connect("changed", lambda *_: self.update_format_button())
        self.filesystem_combobox.connect("changed", lambda *_: self.update_format_button())
        self.format_device_combobox.connect("changed", lambda *_: self.update_format_button())

        self.fsmodel.append(["fat32", "FAT32", 11, True, True])
        self.fsmodel.append(["exfat", "exFAT", 15, False, False])
        self.fsmodel.append(["ntfs", "NTFS", 32, False, False])
        self.fsmodel.append(["ext4", "EXT4", 16, False, False])
        self.filesystem_combobox.set_model(self.fsmodel)

        renderer_text_fs = Gtk.CellRendererText()
        self.filesystem_combobox.pack_start(renderer_text_fs, True)
        self.filesystem_combobox.add_attribute(renderer_text_fs, "text", 1)
        self.filesystem_combobox.set_active(0)

        renderer_text_dev = Gtk.CellRendererText()
        self.format_device_combobox.pack_start(renderer_text_dev, True)
        self.format_device_combobox.add_attribute(renderer_text_dev, "text", 1)
        self.format_device_combobox.set_model(self.format_devicemodel)

    def setup_wipe_mode(self):
        renderer_text_dev = Gtk.CellRendererText()
        self.wipe_device_combobox.pack_start(renderer_text_dev, True)
        self.wipe_device_combobox.add_attribute(renderer_text_dev, "text", 1)
        self.wipe_device_combobox.set_model(self.wipe_devicemodel)

        self.wipe_combo_handler_id = self.wipe_device_combobox.connect("changed", self.wipe_device_selected)
        self.wipe_type_combobox.connect("changed", self.wipe_type_selected)
        self.wipe_button.connect("clicked", self.do_wipe)

    def select_device(self, disk_path, model, combobox):
        if disk_path:
            device_iter = model.get_iter_first()
            while device_iter:
                value = model.get_value(device_iter, 0)
                if disk_path in value:
                    combobox.set_active_iter(device_iter)
                    return
                device_iter = model.iter_next(device_iter)
        
        device_iter = model.get_iter_first()
        if device_iter:
            combobox.set_active_iter(device_iter)

    def print_drive(self, drive):
        if not self.debug: return
        try:
            print(f"--- Drive {drive.get_property('id')} ---")
            for prop in drive.list_properties():
                name = prop.name
                if name in RELEVANT_UDISK_PROPERTIES:
                    print(f"    {prop.name}: {drive.get_property(prop.name)}")
            print()
        except Exception as e:
            print(e)

    def get_devices(self):
        show_all = self.show_all_disks_write_checkbutton.get_active()

        self.write_button.set_sensitive(False)
        self.read_button.set_sensitive(False)
        self.format_button.set_sensitive(False)
        self.wipe_button.set_sensitive(False)
        
        self.write_device_combobox.handler_block(self.write_combo_handler_id)
        self.read_device_combobox.handler_block(self.read_combo_handler_id)
        self.format_device_combobox.handler_block(self.format_combo_handler_id)
        self.wipe_device_combobox.handler_block(self.wipe_combo_handler_id)

        self.write_devicemodel.clear()
        self.read_devicemodel.clear()
        self.format_devicemodel.clear()
        self.wipe_devicemodel.clear()

        self.write_device_combobox.handler_unblock(self.write_combo_handler_id)
        self.read_device_combobox.handler_unblock(self.read_combo_handler_id)
        self.format_device_combobox.handler_unblock(self.format_combo_handler_id)
        self.wipe_device_combobox.handler_unblock(self.wipe_combo_handler_id)

        detected_device_paths = []
        self.selected_write_device = None
        self.selected_read_device = None
        self.selected_format_device = None
        self.selected_wipe_device = None

        manager = self.udisks_client.get_object_manager()
        for obj in manager.get_objects():
            block = obj.get_block()
            if not block: continue
            
            if block.get_property('id-usage') != '':
                continue

            drive = self.udisks_client.get_drive_for_block(block)
            if not drive: continue

            device_path = block.get_property('device')
            if device_path in detected_device_paths:
                continue

            self.print_drive(drive)
            is_usb = str(drive.get_property('connection-bus')) in ['usb', 'cpio', 'sdio']
            
            size = int(block.get_property('size'))
            
            optical = bool(drive.get_property('optical'))
            removable = bool(drive.get_property('removable'))

            if size > 0 and not optical and (show_all or (is_usb and removable) or device_path == self.last_used_device_path):
                drive_vendor = str(drive.get_property('vendor')).strip()
                drive_model = str(drive.get_property('model')).strip()
                display_model = f"{drive_vendor} {drive_model}".strip()

                if size >= 10**12: size_str = f"{size / 10**12:.1f} TB"
                elif size >= 10**9: size_str = f"{size / 10**9:.1f} GB"
                elif size >= 10**6: size_str = f"{size / 10**6:.0f} MB"
                else: size_str = f"{size / 10**3:.0f} KB"

                item = f"{display_model} ({os.path.basename(device_path)}) - {size_str}"
                
                detected_device_paths.append(device_path)
                self.write_devicemodel.append([device_path, item])
                self.read_devicemodel.append([device_path, item])
                self.format_devicemodel.append([device_path, item])
                self.wipe_devicemodel.append([device_path, item])
        
        self.select_device(self.last_used_device_path, self.write_devicemodel, self.write_device_combobox)
        self.select_device(self.last_used_device_path, self.read_devicemodel, self.read_device_combobox)
        self.select_device(self.last_used_device_path, self.format_devicemodel, self.format_device_combobox)
        self.select_device(self.last_used_device_path, self.wipe_devicemodel, self.wipe_device_combobox)

    def write_device_selected(self, widget):
        iterator = widget.get_active_iter()
        if iterator:
            new_path = self.write_devicemodel.get_value(iterator, 0)
            self.selected_write_device = new_path
            if self.last_used_device_path != new_path:
                self.last_used_device_path = new_path
                self.read_device_combobox.handler_block(self.read_combo_handler_id)
                self.select_device(new_path, self.read_devicemodel, self.read_device_combobox)
                self.read_device_combobox.handler_unblock(self.read_combo_handler_id)
                self.selected_read_device = new_path
                
                self.format_device_combobox.handler_block(self.format_combo_handler_id)
                self.select_device(new_path, self.format_devicemodel, self.format_device_combobox)
                self.format_device_combobox.handler_unblock(self.format_combo_handler_id)
                self.selected_format_device = new_path

                self.wipe_device_combobox.handler_block(self.wipe_combo_handler_id)
                self.select_device(new_path, self.wipe_devicemodel, self.wipe_device_combobox)
                self.wipe_device_combobox.handler_unblock(self.wipe_combo_handler_id)
                self.selected_wipe_device = new_path
        else:
            self.selected_write_device = None
        
        self.update_write_button()
        self.update_read_button()
        self.update_format_button()
        self.update_wipe_button()

    def read_device_selected(self, widget):
        iterator = widget.get_active_iter()
        if iterator:
            new_path = self.read_devicemodel.get_value(iterator, 0)
            self.selected_read_device = new_path
            if self.last_used_device_path != new_path:
                self.last_used_device_path = new_path
                self.write_device_combobox.handler_block(self.write_combo_handler_id)
                self.select_device(new_path, self.write_devicemodel, self.write_device_combobox)
                self.write_device_combobox.handler_unblock(self.write_combo_handler_id)
                self.selected_write_device = new_path
                
                self.format_device_combobox.handler_block(self.format_combo_handler_id)
                self.select_device(new_path, self.format_devicemodel, self.format_device_combobox)
                self.format_device_combobox.handler_unblock(self.format_combo_handler_id)
                self.selected_format_device = new_path

                self.wipe_device_combobox.handler_block(self.wipe_combo_handler_id)
                self.select_device(new_path, self.wipe_devicemodel, self.wipe_device_combobox)
                self.wipe_device_combobox.handler_unblock(self.wipe_combo_handler_id)
                self.selected_wipe_device = new_path
        else:
            self.selected_read_device = None

        self.update_write_button()
        self.update_read_button()
        self.update_format_button()
        self.update_wipe_button()

    def format_device_selected(self, widget):
        iterator = widget.get_active_iter()
        if iterator:
            new_path = self.format_devicemodel.get_value(iterator, 0)
            self.selected_format_device = new_path
            if self.last_used_device_path != new_path:
                self.last_used_device_path = new_path
                self.write_device_combobox.handler_block(self.write_combo_handler_id)
                self.select_device(new_path, self.write_devicemodel, self.write_device_combobox)
                self.write_device_combobox.handler_unblock(self.write_combo_handler_id)
                self.selected_write_device = new_path

                self.read_device_combobox.handler_block(self.read_combo_handler_id)
                self.select_device(new_path, self.read_devicemodel, self.read_device_combobox)
                self.read_device_combobox.handler_unblock(self.read_combo_handler_id)
                self.selected_read_device = new_path

                self.wipe_device_combobox.handler_block(self.wipe_combo_handler_id)
                self.select_device(new_path, self.wipe_devicemodel, self.wipe_device_combobox)
                self.wipe_device_combobox.handler_unblock(self.wipe_combo_handler_id)
                self.selected_wipe_device = new_path
        else:
            self.selected_format_device = None
        
        self.update_write_button()
        self.update_read_button()
        self.update_format_button()
        self.update_wipe_button()
   
    def wipe_device_selected(self, widget):
        iterator = widget.get_active_iter()
        if iterator:
            new_path = self.wipe_devicemodel.get_value(iterator, 0)
            self.selected_wipe_device = new_path
            if self.last_used_device_path != new_path:
                self.last_used_device_path = new_path
                self.write_device_combobox.handler_block(self.write_combo_handler_id)
                self.select_device(new_path, self.write_devicemodel, self.write_device_combobox)
                self.write_device_combobox.handler_unblock(self.write_combo_handler_id)
                self.selected_write_device = new_path

                self.read_device_combobox.handler_block(self.read_combo_handler_id)
                self.select_device(new_path, self.read_devicemodel, self.read_device_combobox)
                self.read_device_combobox.handler_unblock(self.read_combo_handler_id)
                self.selected_read_device = new_path

                self.format_device_combobox.handler_block(self.format_combo_handler_id)
                self.select_device(new_path, self.format_devicemodel, self.format_device_combobox)
                self.format_device_combobox.handler_unblock(self.format_combo_handler_id)
                self.selected_format_device = new_path
        else:
            self.selected_wipe_device = None
        
        self.update_write_button()
        self.update_read_button()
        self.update_format_button()
        self.update_wipe_button()
   
    def wipe_type_selected(self, widget):
        wipe_type = self.wipe_type_combobox.get_active_id()
        is_random = (wipe_type == 'random')
        self.wipe_final_zero_checkbutton.set_sensitive(is_random)
        if not is_random:
            self.wipe_final_zero_checkbutton.set_active(False)

    def filesystem_selected(self, widget):
        fs_iter = self.filesystem_combobox.get_active_iter()
        if fs_iter:
            self.filesystem = self.fsmodel.get_value(fs_iter, 0)
            self.label_entry.set_max_length(self.fsmodel.get_value(fs_iter, 2))
            self.on_label_entry_text_changed(self.label_entry)
        self.update_format_button()

    def file_selected(self, widget):
        self.update_write_button()
        self.update_read_button()
        self.update_format_button()
        self.update_wipe_button()

    def update_write_button(self):
        has_file = self.write_file_chooser.get_filename() is not None
        has_device = self.selected_write_device is not None
        self.write_button.set_sensitive(has_file and has_device)

    def update_read_button(self):
        has_file = self.read_target_entry.get_text() != ""
        has_device = self.selected_read_device is not None
        self.read_button.set_sensitive(has_file and has_device)

    def update_format_button(self):
        has_device = self.selected_format_device is not None
        has_fs = self.filesystem_combobox.get_active_iter() is not None
        self.format_button.set_sensitive(has_device and has_fs)
   
    def update_wipe_button(self):
        has_device = self.selected_wipe_device is not None
        self.wipe_button.set_sensitive(has_device)

    def on_label_entry_text_changed(self, widget, data=None):
        self.label_entry.handler_block(self.label_entry_changed_id)
        active_iter = self.filesystem_combobox.get_active_iter()
        text = self.label_entry.get_text()

        if active_iter:
            if self.fsmodel.get_value(active_iter, 3): text = text.upper()
            if self.fsmodel.get_value(active_iter, 4):
                for char in FORBIDDEN_CHARS: text = text.replace(char, "")
        try:
            text = unidecode(text)
        except Exception:
            text = ""

        self.label_entry.set_text(text)
        self.label_entry.handler_unblock(self.label_entry_changed_id)

    def do_format(self, widget):
        if self.debug:
            print(f"DEBUG: Format {self.selected_format_device} as {self.filesystem}")
            return
            
        self.udisks_client.handler_block(self.udisk_listener_id)
        self.set_format_sensitive(False)
        self.set_write_sensitive(False)
        self.set_read_sensitive(False)
        self.set_wipe_sensitive(False)
        self.stack_switcher.set_sensitive(False)
        label = self.label_entry.get_text()
        self.raw_format(self.selected_format_device, self.filesystem, label)

    def check_format_job(self):
        self.process.poll()
        if self.process.returncode is None:
            self.pulse_progress(self.format_progressbar)
            return True
        else:
            return_code = self.process.returncode
            self.process = None
            GLib.idle_add(self.format_job_done, return_code)
            return False

    def raw_format(self, disk_path, fstype, label):
        cmd = ['/usr/bin/driveutility-format', '-d', disk_path,
               '-f', fstype, '-u', str(os.geteuid()), '-g', str(os.getgid()), '--', label]
        if os.geteuid() > 0: cmd.insert(0, 'pkexec')
        self.process = Popen(cmd, shell=False, stdout=PIPE, stderr=PIPE, preexec_fn=os.setsid)
        self.format_progressbar.show()
        self.pulse_progress(self.format_progressbar)
        GLib.timeout_add(500, self.check_format_job)

    def format_job_done(self, rc):
        self.udisks_client.handler_unblock(self.udisk_listener_id)
        self.reset_ui_state()
        if rc == 0:
            self.show_format_result("emblem-ok-symbolic", _('The disk was formatted successfully.'))
        elif rc == 5:
            message = _("An error occured while creating a partition on %s.") % self.selected_format_device
            self.show_format_result("dialog-error-symbolic", message)
        elif rc == 127:
            self.show_format_result("dialog-error-symbolic", _('Authentication Error.'))
        elif rc == 126:
            self.go_back_to_main("format_page")
        else:
            self.show_format_result("dialog-error-symbolic", _('An error occurred.'))
        return False

    def do_wipe(self, widget):
        device = self.selected_wipe_device
        passes = self.wipe_passes_spinbutton.get_value_as_int()
        size = self.wipe_size_spinbutton.get_value_as_int()
        wipe_type = self.wipe_type_combobox.get_active_id()
        final_zero = self.wipe_final_zero_checkbutton.get_active()

        if self.debug:
            print(f"DEBUG: Wipe {device}, type={wipe_type}, passes={passes}, final_zero={final_zero}, size={size}MB")
            return
        
        self.udisks_client.handler_block(self.udisk_listener_id)
        self.set_write_sensitive(False)
        self.set_read_sensitive(False)
        self.set_format_sensitive(False)
        self.set_wipe_sensitive(False)
        self.stack_switcher.set_sensitive(False)
        self.wipe_progressbar.show()
        self.raw_wipe(device, wipe_type, passes, final_zero, size)

    def check_wipe_job(self):
        self.process.poll()
        if self.process.returncode is None:
            self.pulse_progress(self.wipe_progressbar)
            return True
        else:
            return_code = self.process.returncode
            self.process = None
            GLib.idle_add(self.wipe_job_done, return_code)
            return False

    def raw_wipe(self, device, wipe_type, passes, final_zero, size):
        cmd = ['/usr/bin/driveutility-wipe', '-d', device, '-t', wipe_type, '-p', str(passes)]
        if final_zero:
            cmd.append('-z')
        if size > 0:
            cmd.extend(['-s', str(size)])
        if os.geteuid() > 0: cmd.insert(0, 'pkexec')
        
        self.process = Popen(cmd, shell=False, stdout=PIPE, stderr=PIPE, preexec_fn=os.setsid)
        self.pulse_progress(self.wipe_progressbar)
        GLib.timeout_add(500, self.check_wipe_job)

    def wipe_job_done(self, rc):
        self.udisks_client.handler_unblock(self.udisk_listener_id)
        self.reset_ui_state()
        if rc == 0:
            self.show_wipe_result("emblem-ok-symbolic", _('The disk was wiped successfully.'))
        elif rc == 127:
            self.show_wipe_result("dialog-error-symbolic", _('Authentication Error.'))
        elif rc == 126:
            self.go_back_to_main("wipe_page")
        else:
            message = _("An error occurred while wiping %s.") % self.selected_wipe_device
            self.show_wipe_result("dialog-error-symbolic", message)
        return False

    def do_write(self, widget):
        source = self.write_file_chooser.get_filename()
        target = self.selected_write_device
        if self.debug:
            print(f"DEBUG: Write {source} to {target}")
            return
        
        filename = os.path.basename(source).lower()
        for keyword in ["windows", "win7", "win8", "win10", "winxp"]:
            if keyword in filename:
                self.main_stack.set_visible_child_name("windows_page")
                return
        
        self.udisks_client.handler_block(self.udisk_listener_id)
        self.set_write_sensitive(False)
        self.set_read_sensitive(False)
        self.set_format_sensitive(False)
        self.set_wipe_sensitive(False)
        self.stack_switcher.set_sensitive(False)
        self.write_progressbar.show()
        self.raw_write(source, target)

    def do_read(self, widget):
        source = self.selected_read_device
        target = self.read_target_entry.get_text()
        compression = self.compression_combobox.get_active_id()
        if compression == "none":
            compression = None

        if self.debug:
            print(f"DEBUG: Read {source} to {target} with compression {compression}")
            return
            
        self.udisks_client.handler_block(self.udisk_listener_id)
        self.set_write_sensitive(False)
        self.set_read_sensitive(False)
        self.set_format_sensitive(False)
        self.set_wipe_sensitive(False)
        self.stack_switcher.set_sensitive(False)
        self.read_progressbar.show()
        self.raw_read(source, target, compression)

    def set_progress(self, progressbar, size):
        progressbar.set_fraction(size)
        str_progress = f"{float(size) * 100:.0f}%"
        int_progress = int(float(size) * 100)
        progressbar.set_text(str_progress)
        XApp.set_window_progress_pulse(self.window, False)
        XApp.set_window_progress(self.window, int_progress)

    def clear_progress(self, progressbar):
        progressbar.set_fraction(0.0)
        progressbar.set_text("")
        progressbar.hide()
        XApp.set_window_progress_pulse(self.window, False)
        XApp.set_window_progress(self.window, 0)

    def pulse_progress(self, progressbar):
        progressbar.pulse()
        XApp.set_window_progress_pulse(self.window, True)

    def update_progress(self, fd, condition, progressbar, progress_attr):
        if Using_Unity: launcher.set_property("progress_visible", True)
        if condition is GLib.IO_IN:
            line = fd.readline().decode('utf-8')
            try:
                size = float(line.strip())
                current_progress = getattr(self, progress_attr, 0) or 0
                progress = round(size * 100)
                if progress > current_progress:
                    setattr(self, progress_attr, progress)
                    GLib.idle_add(self.set_progress, progressbar, size)
                    if Using_Unity: launcher.set_property("progress", size)
            except (ValueError, TypeError):
                pass
            return True
        else:
            if self.source_id:
                GLib.source_remove(self.source_id)
                self.source_id = None
            return False
            
    def raw_write(self, source, target):
        _, compression = self.get_opener_by_magic(source)
        cmd = ['/usr/bin/driveutility-write', '-s', source, '-t', target]
        if os.geteuid() > 0: cmd.insert(0, 'pkexec')
        self.process = Popen(cmd, shell=False, stdout=PIPE, stderr=PIPE, preexec_fn=os.setsid)
        self.write_progress = 0
        if compression:
             self.source_id = None
             GLib.timeout_add(100, self.check_write_job_pulsing)
        else:
             self.source_id = GLib.io_add_watch(self.process.stdout, GLib.IO_IN | GLib.IO_HUP, self.update_progress, self.write_progressbar, "write_progress")
             GLib.timeout_add(500, self.check_write_job)

    def check_write_job(self):
        self.process.poll()
        if self.process.returncode is None:
            return True
        else:
            return_code = self.process.returncode
            self.process = None
            GLib.idle_add(self.write_job_done, return_code)
            return False
            
    def check_write_job_pulsing(self):
        self.pulse_progress(self.write_progressbar)
        return self.check_write_job()
        
    def raw_read(self, source, target, compression):
        cmd = ['/usr/bin/driveutility-read', '-s', source, '-t', target,
            '-u', str(os.geteuid()), '-g', str(os.getgid())]
        if compression:
            cmd.extend(['-c', compression])
        if os.geteuid() > 0:
            cmd.insert(0, 'pkexec')
        
        self.process = Popen(cmd, shell=False, stdout=PIPE, stderr=PIPE, preexec_fn=os.setsid)
        self.read_progress = 0
        self.source_id = GLib.io_add_watch(self.process.stdout, GLib.IO_IN | GLib.IO_HUP, self.update_progress, self.read_progressbar, "read_progress")
        GLib.timeout_add(500, self.check_read_job)

    def check_read_job(self):
        self.process.poll()
        if self.process.returncode is None:
            return True
        else:
            return_code = self.process.returncode
            self.process = None
            GLib.idle_add(self.read_job_done, return_code)
            return False

    def get_opener_by_magic(self, file_path):
        MAGIC_NUMBERS = {
            b'\x1f\x8b': 'gzip',
            b'BZh': 'bzip2',
            b'\xfd7zXZ\x00': 'xz',
            b'\x04"M\x18': 'lz4',
            b'(\xb5/\xfd': 'zstd'
        }
        try:
            with open(file_path, 'rb') as f:
                header = f.read(16)
                for magic, name in MAGIC_NUMBERS.items():
                    if header.startswith(magic):
                        return open, name
        except (IOError, FileNotFoundError):
            return None, None
        return open, None

    def write_job_done(self, rc):
        self.udisks_client.handler_unblock(self.udisk_listener_id)
        self.reset_ui_state()
        if Using_Unity: launcher.set_property("progress_visible", False)
        
        if rc == 0:
            if Using_Unity: launcher.set_property("urgent", True)
            self.set_progress(self.write_progressbar, 1.0)
            self.show_write_result("emblem-ok-symbolic", _('The image was successfully written to the disk.'))
        elif rc == 3:
            self.show_write_result("dialog-error-symbolic", _('Not enough space on the destination disk.'))
        elif rc == 4:
            self.show_write_result("dialog-error-symbolic", _('An error occured while writing the image.'))
        elif rc == 127:
            self.show_write_result("dialog-error-symbolic", _('Authentication Error.'))
        elif rc == 126:
            self.go_back_to_main("write_page")
        else:
            self.show_write_result("dialog-error-symbolic", _('An error occurred.'))
        return False

    def read_job_done(self, rc):
        self.udisks_client.handler_unblock(self.udisk_listener_id)
        self.reset_ui_state()
        if Using_Unity: launcher.set_property("progress_visible", False)
        
        if rc == 0:
            if Using_Unity: launcher.set_property("urgent", True)
            self.set_progress(self.read_progressbar, 1.0)
            self.show_read_result("emblem-ok-symbolic", _('The image was successfully created.'))
        elif rc == 4:
            self.show_read_result("dialog-error-symbolic", _('An error occured while creating the image.'))
        elif rc == 127:
            self.show_read_result("dialog-error-symbolic", _('Authentication Error.'))
        elif rc == 126:
            self.go_back_to_main("read_page")
        else:
            self.show_read_result("dialog-error-symbolic", _('An error occurred.'))
        return False

    def show_format_result(self, icon_name, text):
        self.main_stack.set_visible_child_name("format_result_page")
        self.wTree.get_object("format_result_image").set_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        self.wTree.get_object("format_result_label").set_text(text)

    def show_write_result(self, icon_name, text):
        self.main_stack.set_visible_child_name("write_result_page")
        self.wTree.get_object("write_result_image").set_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        self.wTree.get_object("write_result_label").set_text(text)
        
    def show_read_result(self, icon_name, text):
        self.main_stack.set_visible_child_name("read_result_page")
        self.wTree.get_object("read_result_image").set_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        self.wTree.get_object("read_result_label").set_text(text)

    def show_wipe_result(self, icon_name, text):
        self.main_stack.set_visible_child_name("wipe_result_page")
        self.wTree.get_object("wipe_result_image").set_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        self.wTree.get_object("wipe_result_label").set_text(text)

    def close(self, widget):
        if self.process:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except OSError:
                pass
        Gtk.main_quit()

    def set_all_modes_sensitive(self, sensitive):
        self.set_write_sensitive(sensitive)
        self.set_read_sensitive(sensitive)
        self.set_format_sensitive(sensitive)
        self.set_wipe_sensitive(sensitive)

    def set_write_sensitive(self, sensitive):
        self.write_file_chooser.set_sensitive(sensitive)
        self.write_device_combobox.set_sensitive(sensitive)
        self.write_button.set_sensitive(sensitive)
        self.show_all_disks_write_checkbutton.set_sensitive(sensitive)
        self.stack_switcher.set_sensitive(sensitive)
        if sensitive:
            self.update_write_button()

    def set_read_sensitive(self, sensitive):
        self.read_target_button.set_sensitive(sensitive)
        self.read_device_combobox.set_sensitive(sensitive)
        self.read_target_entry.set_sensitive(sensitive)
        self.compression_combobox.set_sensitive(sensitive)
        self.show_all_disks_read_checkbutton.set_sensitive(sensitive)
        self.stack_switcher.set_sensitive(sensitive)
        if sensitive:
            self.update_read_button()

    def set_format_sensitive(self, sensitive):
        self.filesystem_combobox.set_sensitive(sensitive)
        self.format_device_combobox.set_sensitive(sensitive)
        self.label_entry.set_sensitive(sensitive)
        self.format_button.set_sensitive(sensitive)
        self.show_all_disks_format_checkbutton.set_sensitive(sensitive)
        self.stack_switcher.set_sensitive(sensitive)
        if sensitive:
            self.update_format_button()
    
    def set_wipe_sensitive(self, sensitive):
        self.wipe_device_combobox.set_sensitive(sensitive)
        self.wipe_type_combobox.set_sensitive(sensitive)
        self.wipe_passes_spinbutton.set_sensitive(sensitive)
        self.wipe_size_spinbutton.set_sensitive(sensitive)
        self.wipe_final_zero_checkbutton.set_sensitive(sensitive and self.wipe_type_combobox.get_active_id() == 'random')
        self.wipe_button.set_sensitive(sensitive)
        self.show_all_disks_wipe_checkbutton.set_sensitive(sensitive)
        self.stack_switcher.set_sensitive(sensitive)
        if sensitive:
            self.update_wipe_button()

if __name__ == "__main__":
    disk_path = None
    image_path = None
    filesystem = None
    mode = None
    debug = False

    def usage():
        print("Usage: driveutility [--debug] [-m mode] [-i image_path] [-d disk_device] [-f filesystem]")
        print("   -m, --mode: 'write', 'read', 'format' or 'wipe' to open on a specific tab.")
        exit(0)

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hm:i:d:f:", ["debug", "help", "mode=", "image=", "disk=", "filesystem="])
    except getopt.GetoptError as msg:
        print(msg)
        print("for help use --help")
        sys.exit(2)

    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
        elif o in ("-m", "--mode"):
            if a in ("write", "read", "format", "wipe"):
                mode = a
        elif o in ("-i", "--image"):
            image_path = a
        elif o in ("-d", "--disk"):
            disk_path = ''.join([i for i in a if not i.isdigit()])
        elif o in ("-f", "--filesystem"):
            filesystem = a
        elif o == "--debug":
            debug = True

    DriveUtility(image_path, disk_path, filesystem, mode, debug)
    Gtk.main()