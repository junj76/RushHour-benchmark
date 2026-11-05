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
        xml = device.dump_hierarchy(compressed=False)
        root = ET.fromstring(xml)
        nodes = list(root.iter("node"))
        # 只拒绝明确属于本次目标应用的通知请求，不操作其他权限。
        aliases = {"com.pinterest": "Pinterest", "com.instagram.android": "Instagram",
                   "tv.twitch.android.app": "Twitch"}
        notification = any(
            n.get("resource-id") == "com.android.permissioncontroller:id/permission_message"
            and ("通知" in n.get("text", "") or "notifications" in n.get("text", "").lower())
            and any(aliases.get(p, "__unknown__").lower() in n.get("text", "").lower()
                    for p in allowed) for n in nodes)
        if notification:
            deny = next((n.get("resource-id") for n in nodes if n.get("resource-id") in {
                "com.android.permissioncontroller:id/permission_deny_button",
                "com.android.permissioncontroller:id/permission_deny_and_dont_ask_again_button"}
                and n.get("enabled") == "true"), None)
            if deny:
                device(resourceId=deny).click(timeout=0.5)
                time.sleep(0.2)
                if time.monotonic() >= deadline:
                    raise RuntimeError("通知弹窗处理超时，请检查当前页面")
                continue
        google_text = " ".join(n.get("text", "") for n in nodes
                               if n.get("package") == "com.google.android.gms")
        if "验证身份" in google_text and "重新登录" in google_text:
            raise RuntimeError("Google账号要求人工验证身份并重新登录；请先在手机上处理，再继续测试")
        visible = visible_ui_packages(xml)
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
