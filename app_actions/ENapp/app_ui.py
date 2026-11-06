"""Check the exposed application UI without app_current() or device actions."""
import re
import time
import xml.etree.ElementTree as ET


def visible_ui_packages(xml_text):
    """Return packages with nonempty, visible nodes in the current UI tree."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError("Invalid UI XML: " + str(exc)) from exc

    packages = set()

    def visit(node, parent_visible=True):
        visible = parent_visible and node.get("visible-to-user") != "false"
        if not visible:
            return
        package = node.get("package", "")
        bounds = re.fullmatch(
            r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]",
            node.get("bounds", ""),
        )
        if package and bounds:
            left, top, right, bottom = map(int, bounds.groups())
            if right > left and bottom > top:
                packages.add(package)
        for child in node:
            visit(child, visible)

    visit(root)
    return sorted(packages)


def require_app_ui(device, packages, timeout=10):
    """Wait for one allowed package in UI XML; this does not prove input focus."""
    allowed = [packages] if isinstance(packages, str) else list(packages)
    if not allowed:
        raise ValueError("Expected at least one application package")
    deadline = time.monotonic() + timeout
    while True:
        visible = visible_ui_packages(device.dump_hierarchy(compressed=False))
        matches = [package for package in allowed if package in visible]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError("Multiple allowed apps are visible: " + repr(matches))
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Target app UI not detected. Expected: " + repr(allowed)
                + "; visible UI packages: " + repr(visible)
            )
        time.sleep(0.15)
