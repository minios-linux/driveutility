import xml.etree.ElementTree as ET
from pathlib import Path


UI_PATH = (Path(__file__).resolve().parents[1] / "share" / "driveutility" /
           "driveutility.ui")


def _property(widget, name):
    for prop in widget.findall("property"):
        if prop.get("name") == name:
            return prop.text or ""
    return ""


def test_mnemonic_markers_are_enabled_exactly_once():
    root = ET.parse(str(UI_PATH)).getroot()

    for widget in root.iter("object"):
        label = _property(widget, "label")
        if not label or not _property(widget, "use_underline"):
            assert "_" not in label
            continue
        assert label.count("_") == 1


def test_mnemonics_are_unique_within_each_page():
    root = ET.parse(str(UI_PATH)).getroot()
    pages = ("write_page_container", "read_page_container",
             "format_page_container", "wipe_page_container",
             "write_result_page", "read_result_page",
             "format_result_page", "wipe_result_page", "windows_page")

    for page_id in pages:
        page = next(widget for widget in root.iter("object")
                    if widget.get("id") == page_id)
        keys = []
        for widget in page.iter("object"):
            label = _property(widget, "label")
            if _property(widget, "use_underline"):
                marker = label.index("_")
                keys.append(label[marker + 1].casefold())
        assert len(keys) == len(set(keys)), page_id
