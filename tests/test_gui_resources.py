from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
UI_PATH = ROOT / "share" / "driveutility" / "driveutility.ui"


def _style_classes(widget):
    style = widget.find("style")
    if style is None:
        return set()
    return {item.get("name") for item in style.findall("class")}


def test_gui_uses_minios_gui_1_4_runtime_dependency():
    source = (ROOT / "lib" / "driveutility.py").read_text()
    control = (ROOT / "debian" / "control").read_text()

    assert "from minios_gui import" in source
    assert "HelpPopoverButton" in source
    assert "apply_minios_css()" in source
    assert "new_icon" in source
    assert "python3-minios-gui (>= 1.4.0)" in control


def test_builder_uses_shared_header_and_context_help_container():
    root = ET.parse(str(UI_PATH)).getroot()
    widgets = {widget.get("id"): widget for widget in root.iter("object")}

    assert widgets["main_headerbar"].get("class") == "GtkHeaderBar"
    assert "minios-headerbar" in _style_classes(widgets["main_headerbar"])
    assert widgets["wipe_method_help_container"].get("class") == "GtkBox"
    assert "wipe_method_info" not in widgets


def test_shared_resources_are_not_duplicated_locally():
    source = (ROOT / "lib" / "driveutility.py").read_text()

    assert not (ROOT / "lib" / "gui.py").exists()
    assert not (ROOT / "share" / "driveutility" / "driveutility.css").exists()
    assert "apply_app_css" not in source
    assert "theme_icon" not in source


def test_erase_help_uses_shared_keyboard_accessible_popover():
    source = (ROOT / "lib" / "driveutility.py").read_text()

    assert "self.wipe_method_help = HelpPopoverButton(" in source
    assert '_("Erase methods")' in source
    assert "sections=(" in source
    assert "compact=True" in source
    assert "set_tooltip_text" not in source[source.index(
        "def setup_wipe_mode"):source.index("def _wipe_capabilities_for")]
