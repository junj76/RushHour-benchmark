"""Execute one fixed app scenario from an already-open home page."""
import argparse
from datetime import datetime
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
EXIT_CODES = {"PASS": 0, "FAIL": 1, "NOT_AT_HOME": 2, "NEEDS_CONFIGURATION": 3}


class NotAtHome(RuntimeError):
    pass


class NeedsConfiguration(RuntimeError):
    pass

_OCR_ENGINE = None


def get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE

def bounds(value):
    match = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", value)
    return tuple(map(int, match.groups())) if match else (0, 0, 0, 0)


def matches(attrs, selector):
    keys = {"text": "text", "description": "content-desc",
            "resourceId": "resource-id", "className": "class",
            "clickable": "clickable", "selected": "selected"}
    for key, expected in selector.items():
        if key in {"below", "above", "alignedWith", "within", "minYRatio", "maxYRatio"}:
            continue
        if key in keys:
            actual = attrs.get(keys[key], "")
            if isinstance(expected, bool):
                expected = str(expected).lower()
            if actual != expected:
                return False
        elif key.endswith("Contains"):
            base = key[:-8]
            if base not in keys or expected not in attrs.get(keys[base], ""):
                return False
        elif key.endswith("Matches"):
            base = key[:-7]
            if base not in keys or not re.fullmatch(expected, attrs.get(keys[base], "")):
                return False
        else:
            raise ValueError("Unknown selector field: " + key)
    return True


class Scenario:
    def __init__(self, device, profile, folder, timeout=12.0, device_info=None):
        self.d = device
        self.profile = profile
        self.package = profile["package"]
        self.folder = folder
        self.timeout = timeout
        self.evidence_errors = []
        self.cached_window_size = None
        if profile.get("cache_window_size", False):
            info = device_info or {}
            width, height = info.get("displayWidth"), info.get("displayHeight")
            if (profile.get("native_window_size", False)
                    and isinstance(width, int) and width > 0
                    and isinstance(height, int) and height > 0):
                self.cached_window_size = (width, height)
            else:
                self.cached_window_size = self.d.window_size()

    def tree(self):
        import time

        deadline = time.monotonic() + min(3.0, self.timeout)
        while True:
            if self.profile.get("fast_mode", False):
                info = self.d.info
                package = info.get("currentPackageName")
                current = (
                    {"package": package}
                    if package else self.d.app_current()
                )
            else:
                current = self.d.app_current()
            if current.get("package") == self.package:
                return ET.fromstring(self.d.dump_hierarchy(**self.profile.get("hierarchy", {"compressed": True})))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    "Target app is no longer foreground: "
                    f"expected={self.package!r}, actual={current!r}"
                )
            time.sleep(min(0.2, remaining))

    def candidates(self, tree, selector):
        width, height = (
            self.cached_window_size or self.d.window_size()
        )
        containers = None
        if "within" in selector:
            containers = self.candidates(tree, selector["within"])
        parents = {child: parent for parent in tree.iter() for child in parent}
        lower, upper = 0, height
        aligned_bounds = None
        if "alignedWith" in selector:
            anchors = self.candidates(tree, selector["alignedWith"])
            if len(anchors) != 1:
                return []
            aligned_bounds = bounds(anchors[0].get("bounds", ""))
        for key in ("below", "above"):
            if key in selector:
                anchors = self.candidates(tree, selector[key])
                if len(anchors) != 1:
                    return []
                anchor = bounds(anchors[0].get("bounds", ""))
                if key == "below":
                    lower = anchor[3]
                else:
                    upper = anchor[1]
        found = []
        seen = set()
        for node in tree.iter("node"):
            if containers is not None:
                ancestor = parents.get(node)
                while ancestor is not None and ancestor not in containers:
                    ancestor = parents.get(ancestor)
                if ancestor is None:
                    continue
            attrs = node.attrib
            if attrs.get("package") != self.package:
                continue
            if attrs.get("visible-to-user", "true") == "false" or attrs.get("enabled") == "false":
                continue
            left, top, right, bottom = bounds(attrs.get("bounds", ""))
            if not (right > left and bottom > top and right > 0 and bottom > 0
                    and left < width and top < height):
                continue
            if top < lower or bottom > upper:
                continue
            if aligned_bounds and (bottom <= aligned_bounds[1] or top >= aligned_bounds[3]):
                continue
            center_y = (top + bottom) / (2 * height)
            if center_y < selector.get("minYRatio", 0) or center_y > selector.get("maxYRatio", 1):
                continue
            if matches(attrs, selector):
                # Nested accessibility nodes may represent the same on-screen target.
                signature = (attrs.get("bounds"), attrs.get("text"), attrs.get("content-desc"))
                if signature not in seen:
                    seen.add(signature)
                    found.append(node)
        return sorted(found, key=lambda n: (bounds(n.get("bounds"))[1],
                                            bounds(n.get("bounds"))[0]))

    def find(self, selectors, first=False, timeout=None, with_tree=False):
        if not selectors:
            raise NeedsConfiguration("A selector is missing from the app profile")
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            tree = self.tree()
            for selector in selectors:
                found = self.candidates(tree, selector)
                if len(found) == 1 or (found and first):
                    return (found[0], tree) if with_tree else found[0]
            if time.monotonic() >= deadline:
                raise RuntimeError("Control absent or ambiguous: " + json.dumps(selectors, ensure_ascii=False))
            time.sleep(0.4)

    def expect_native_groups(self, groups, timeout=5):
        allowed = {
            "text", "textContains", "description",
            "descriptionContains", "resourceId", "className",
        }
        if not groups or any(not group for group in groups):
            raise ValueError("Empty expectation groups")

        controls = []
        for group in groups:
            alternatives = []
            for selector in group:
                if not selector or not set(selector).issubset(allowed):
                    raise ValueError("Unsupported native selector")
                alternatives.append(
                    self.d(packageName=self.package, **selector)
                )
            controls.append(alternatives)

        deadline = time.monotonic() + timeout
        while True:
            # 每组至少一个匹配，所有组都必须满足。
            if all(
                any(control.exists(timeout=0) for control in group)
                for group in controls
            ):
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Expected page not reached: %r" % groups
                )
            time.sleep(self.profile.get("poll_interval", 0.15))

    def expect(self, groups, timeout=None):
        if not groups or any(not group for group in groups):
            raise NeedsConfiguration("Expected-page selectors are missing")
        deadline = time.monotonic() + (
            self.timeout if timeout is None else timeout
        )
        while True:
            tree = self.tree()
            if all(
                any(self.candidates(tree, selector) for selector in group)
                for group in groups
            ):
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Expected page not reached: "
                    + json.dumps(groups, ensure_ascii=False)
                )
            time.sleep(self.profile.get("poll_interval", 0.4))
    def expect_native(self, groups):
        deadline = time.monotonic() + self.timeout
        while True:
            package = (
                self.d.info.get("currentPackageName")
                or self.d.app_current().get("package")
            )
            if package != self.package:
                raise RuntimeError("App left foreground")

            width, height = (
                self.cached_window_size or self.d.window_size()
            )
            passed = True
            for group in groups:
                matched = False
                for selector in group:
                    query = {
                        k: v for k, v in selector.items()
                        if k not in {"minYRatio", "maxYRatio"}
                    }
                    allowed = {
                        "resourceId", "text", "description", "className",
                        "clickable", "selected"
                    }
                    if not set(query).issubset(allowed):
                        raise NeedsConfiguration(
                            "Unsupported native expectation: " + str(query)
                        )
                    controls = self.d(packageName=self.package, **query)
                    for index in range(controls.count):
                        info = controls[index].info
                        box = info.get("visibleBounds") or info["bounds"]
                        center_y = (box["top"] + box["bottom"]) / (2 * height)
                        if (
                            info.get("enabled", True)
                            and box["right"] > box["left"]
                            and box["bottom"] > box["top"]
                            and box["right"] > 0 and box["left"] < width
                            and box["bottom"] > 0 and box["top"] < height
                            and selector.get("minYRatio", 0) <= center_y
                            <= selector.get("maxYRatio", 1)
                        ):
                            matched = True
                            break
                    if matched:
                        break
                if not matched:
                    passed = False
                    break
            if passed:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("Expected page not reached")
            time.sleep(self.profile.get("poll_interval", 0.15))

    def click(self, step):
        if step.get("native_click"):
            allowed = {"resourceId", "className", "text", "textContains",
                       "description", "descriptionContains", "clickable"}
            selectors = step["selectors"]
            if any(not s or not set(s).issubset(allowed) for s in selectors):
                raise NeedsConfiguration("Unsupported native click selector")
            deadline = time.monotonic() + step.get("click_timeout", 2)
            while True:
                for selector in selectors:
                    control = self.d(packageName=self.package, **selector)
                    if control.count != 1:
                        continue
                    info = control.info
                    box = info.get("visibleBounds") or info["bounds"]
                    width, height = self.cached_window_size or self.d.window_size()
                    if not (0 <= box["left"] < box["right"] <= width
                            and 0 <= box["top"] < box["bottom"] <= height):
                        raise RuntimeError("Native click target has no visible bounds")
                    if ((box["right"] - box["left"]) * (box["bottom"] - box["top"])
                            > width * height * 0.65):
                        raise RuntimeError("Native click target is too large")
                    control.click(timeout=max(0, deadline - time.monotonic()))
                    return {"text": info.get("text", ""),
                            "description": info.get("contentDescription", ""),
                            "resource_id": info.get("resourceName", ""),
                            "bounds": box, "method": "native_control_click"}
                if time.monotonic() >= deadline:
                    raise RuntimeError("Native click target absent or ambiguous")
                time.sleep(self.profile.get("poll_interval", 0.15))
        if self.profile.get("fast_mode", False):
            node, tree = self.find(
                step["selectors"],
                first=step.get("pick") == "first",
                with_tree=True,
            )
        else:
            node = self.find(
                step["selectors"], first=step.get("pick") == "first"
            )
            tree = self.tree()
        # Reacquire against the current hierarchy, so bounds are not taken from a stale screen.
        targets = []
        for selector in step["selectors"]:
            found = self.candidates(tree, selector)
            if len(found) == 1 or (found and step.get("pick") == "first"):
                targets = found
                break
        if not targets or (len(targets) > 1 and step.get("pick") != "first"):
            raise RuntimeError("Click target became ambiguous or disappeared")
        node = targets[0]

        target = node
        if step.get("clickBounds") is not True:
            parents = {child: parent for parent in tree.iter() for child in parent}
            while target.get("clickable") != "true":
                target = parents.get(target)
                if target is None or target.get("package") != self.package:
                    raise RuntimeError("No clickable ancestor for requested control")

        x1, y1, x2, y2 = bounds(target.get("bounds", ""))
        width, height = (
            self.cached_window_size or self.d.window_size()
        )
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(width, x2), min(height, y2)

        if x2 <= x1 or y2 <= y1:
            raise RuntimeError("Click target has no visible bounds")
        if (x2 - x1) * (y2 - y1) > width * height * 0.65:
            raise RuntimeError("Click target is too large; calibrate this selector")

        ratio = step.get("clickRatio")
        if ratio is None:
            x, y = (x1 + x2) // 2, (y1 + y2) // 2
        else:
            if (
                not isinstance(ratio, list)
                or len(ratio) != 2
                or not all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in ratio)
            ):
                raise NeedsConfiguration("clickRatio must contain two numbers from 0 to 1")
            x = round(x1 + (x2 - x1) * ratio[0])
            y = round(y1 + (y2 - y1) * ratio[1])

        self.d.click(x, y)

        return {"text": node.get("text", ""), "description": node.get("content-desc", ""),
                "resource_id": node.get("resource-id", ""), "bounds": target.get("bounds")}

    def capture(self, label):
        if self.profile.get("evidence") == "final" and label not in {
            "final", "failure", "recovery_home", "recovery_failure"
        }:
            return
        for suffix in ("xml", "png"):
            if (
                suffix == "xml"
                and label == "final"
                and self.profile.get("success_evidence") == "screenshot"
            ):
                continue
            try:
                path = self.folder / (label + "." + suffix)
                if suffix == "xml":
                    path.write_text(self.d.dump_hierarchy(**self.profile.get("hierarchy", {"compressed": True})), encoding="utf-8")
                else:
                    self.d.screenshot(str(path))
            except Exception as exc:
                self.evidence_errors.append("%s.%s: %s" % (label, suffix, exc))

    def page_signature(self, tree):
        return tuple(sorted(
            (node.get("resource-id", ""), node.get("text", ""),
             node.get("content-desc", ""), node.get("selected", ""),
             node.get("focused", ""), node.get("bounds", ""))
            for node in tree.iter("node") if node.get("package") == self.package
        ))

    def wait_for_page_change(self, before):
        deadline = time.monotonic() + self.timeout
        while True:
            if self.page_signature(self.tree()) != before:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("Action sent, but UI state did not change")
            time.sleep(0.4)

    def execute(self, step):
        action = step["action"]
        detail = {}
        before = (
            self.page_signature(self.tree())
            if not self.profile.get("fast_mode", False)
            and action in {"click", "tap", "back", "enter"}
            else None
        )
        if action == "click_ocr":
            import numpy as np
            engine = get_ocr_engine()   
            deadline = time.monotonic() + 20
            while True:
                # self.tree()
                screen = self.d.screenshot().convert("RGB")
                rows, _ = engine(np.asarray(screen)[:, :, ::-1].copy())
                hits = [(box, text) for box, text, score in (rows or [])
                        if score >= 0.6 and re.fullmatch(
                            step["text_pattern"], re.sub(r"\s+", "", text))]
                screen_height = screen.height
                hits = [
                    hit for hit in hits
                    if step.get("minYRatio", 0)
                    <= np.asarray(hit[0])[:, 1].mean() / screen_height
                    <= step.get("maxYRatio", 1)
                ]
                hits.sort(key=lambda hit: (
                    np.asarray(hit[0])[:, 1].mean(),
                    np.asarray(hit[0])[:, 0].mean(),
                ))
                if len(hits) == 1 or (
                    hits and step.get("pick") == "first"
                ):
                    # self.tree()
                    if screen.size != self.d.window_size():
                        raise RuntimeError("Screenshot/window size mismatch")
                    box, text = hits[0]
                    x, y = np.asarray(box).mean(axis=0)
                    self.d.click(int(x), int(y))
                    detail = {"text": text, "method": "ocr"}
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("OCR target absent or ambiguous")
                time.sleep(0.5)
        elif action == "click":
            phase_started = time.monotonic()
            detail = self.click(step)
            if step.get("trace_timing"):
                detail["click_seconds"] = round(
                    time.monotonic() - phase_started, 3
                )
            if step.get("verify_topic"):
                topic = detail["text"].strip().strip("#").strip()
                if not topic:
                    raise RuntimeError("Topic title is empty")
                title_id = "com.sina.weibo:id/tv_search_result_title_text"
                try:
                    title = self.find([{
                        "resourceId": title_id,
                        "textMatches": r"#?\s*" + re.escape(topic) + r"\s*#?",
                    }], first=True)
                except RuntimeError as exc:
                    actual = self.find(
                        [{"resourceId": title_id}], first=True, timeout=1
                    ).get("text", "")
                    raise RuntimeError(
                        f"Topic title mismatch: expected={topic!r}, actual={actual!r}"
                    ) from exc
                detail["verified_topic"] = topic
                detail["actual_title"] = title.get("text", "")
        elif action == "input_focused":
            time.sleep(float(step.get("wait_seconds", 0)))
            value = str(step["value"])

            if value != "test":
                raise NeedsConfiguration(
                    "netdisk requires the fixed keyword test"
                )

            width, height = self.d.window_size()

            # 百度网盘搜索页顶部输入区域
            self.d.click(
                int(width * 0.35),
                int(height * 0.10),
            )
            time.sleep(0.15)

            response = self.d.shell([
                "input",
                "text",
                value,
            ])
            if response.exit_code != 0:
                raise RuntimeError(
                    "Android text input failed: " + response.output
                )

            detail = {
                "value": value,
                "method": "coordinate_tap_android_input",
            }

        elif action == "ime_search":
            width, height = self.d.window_size()

            # 搜索页右上角蓝色“搜索”按钮
            self.d.click(
                int(width * 0.85),
                int(height * 0.125),
            )
            time.sleep(0.25)

            detail = {
                "method": "coordinate_search_button",
            }
        elif action == "input":
            if step.get("native_input"):
                selectors = step["selectors"]
                allowed = {"resourceId", "className", "text", "description", "focused", "enabled"}
                if any(not s or not set(s).issubset(allowed) for s in selectors):
                    raise NeedsConfiguration("Unsupported native input selector")
                controls = [self.d(packageName=self.package, **s) for s in selectors]
                deadline = time.monotonic() + step.get("input_timeout", 2)
                while True:
                    control = next((c for c in controls if c.count == 1), None)
                    if control is not None:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Input control absent or ambiguous")
                    time.sleep(self.profile.get("poll_interval", 0.15))
                control.set_text(step["value"])

                if step.get("verify_input", True):
                    deadline = (
                        time.monotonic()
                        + step.get("input_timeout", 2)
                    )
                    while True:
                        actual = control.get_text()
                        if actual == step["value"]:
                            break
                        if time.monotonic() >= deadline:
                            raise RuntimeError(
                                "Input mismatch: expected=%r actual=%r"
                                % (step["value"], actual)
                            )
                        time.sleep(
                            self.profile.get("poll_interval", 0.15)
                        )

                    detail = {
                        "value": step["value"],
                        "actual": actual,
                        "method": "native_set_text"
                    }
                else:
                    detail = {
                        "value": step["value"],
                        "method": "native_set_text",
                        "verification": "skipped"
                    }
            else:
                node = self.find(step["selectors"])
                attrs = node.attrib
                selector = {"packageName": self.package, "className": attrs.get("class")}
                if attrs.get("resource-id"):
                    selector["resourceId"] = attrs["resource-id"]
                if attrs.get("focused") == "true":
                    selector["focused"] = True
                control = self.d(**selector)
                if control.count != 1:
                    raise RuntimeError("Input control is ambiguous")
                control.set_text(step["value"])
                verification = {"className": attrs.get("class"), "text": step["value"]}
                if attrs.get("resource-id"):
                    verification["resourceId"] = attrs["resource-id"]
                # ElementTree leaf nodes are falsey even when they exist.
                self.find([verification], timeout=3)
                detail = {"value": step["value"]}
        elif action == "back_until_home" and step.get("native_home"):
            limit = step.get("max_back", 6)
            selector = step["native_home"]
            for count in range(limit + 1):
                info = self.d.info
                package = (
                    info.get("currentPackageName")
                    or self.d.app_current().get("package")
                )
                if package != self.package:
                    raise RuntimeError("App left foreground during return")

                control = self.d(packageName=self.package, **selector)
                reached = False
                match_count = control.count

                if match_count == 1 or (
                    match_count > 1 and step.get("pick") == "first"
                ):
                    target = control[0] if match_count > 1 else control
                    node = target.info
                    box = node.get("visibleBounds") or node["bounds"]
                    width, height = (
                        self.cached_window_size or self.d.window_size()
                    )
                    reached = (
                        node.get("enabled", True)
                        and 0 <= box["left"] < box["right"] <= width
                        and 0 <= box["top"] < box["bottom"] <= height
                        and step.get("home_min_y_ratio", 0)
                        <= (box["top"] + box["bottom"]) / (2 * height)
                        <= step.get("home_max_y_ratio", 0.45)
                    )
                if reached:
                    detail = {"back_count": count, "method": "native"}
                    break
                if count == limit:
                    raise RuntimeError("Home not reached")
                self.d.press("back")
                time.sleep(step.get("back_delay", 0.1))
        elif action == "back_until_home":
            limit = step.get("max_back", 6)
            recovered = False
            for count in range(limit + 1):
                if self.d.app_current().get("package") != self.package:
                    if self.package != "com.sina.weibo" or recovered:
                        raise RuntimeError(
                            "App left foreground: "
                            + str(self.d.app_current())
                        )
                    self.d.app_start(self.package, stop=False)
                    recovered = True
                    time.sleep(2)

                try:
                    self.expect(
                        step["expect"],
                        timeout=step.get("home_check_timeout", 0.8),
                    )
                except RuntimeError:
                    pass
                else:
                    detail = {
                        "back_count": count,
                        "recovered_foreground": recovered,
                    }
                    break

                navigation = step.get("home_navigation")
                if navigation:
                    try:
                        self.find(navigation, timeout=0.8)
                    except RuntimeError:
                        pass
                    else:
                        self.click({
                            "selectors": navigation,
                            "clickBounds": True,
                        })
                        self.expect(step["expect"])
                        detail = {
                            "back_count": count,
                            "clicked_home": True,
                            "recovered_foreground": recovered,
                        }
                        break

                if count == limit:
                    raise RuntimeError(
                        "Home not reached after %d Back presses" % limit
                    )
                self.d.press("back")
                time.sleep(step.get("back_delay", 1))
        elif action == "swipe_up":
            phase_started = time.monotonic()
            width, height = (
                self.cached_window_size or self.d.window_size()
            )
            d_width = int(width * 0.5)
            self.d.swipe(
                d_width, int(height * 0.75),
                d_width, int(height * 0.35),
                duration=0.25,
            )
            detail = {
                "direction": "up",
                "duration": 0.25,
                "gesture_seconds": round(
                    time.monotonic() - phase_started, 3
                ),
            }
        elif action == "swipe_right":
            width, height = (
                self.cached_window_size or self.d.window_size()
            )
            duration = step.get("duration", 0.2)
            self.d.swipe(
                max(1, int(width * 0.01)), int(height * 0.5),
                int(width * 0.65), int(height * 0.5),
                duration=duration,
            )
            detail = {
                "direction": "right",
                "duration": duration,
            }
        elif action == "weibo_return_home":
            width, height = (
                self.cached_window_size or self.d.window_size()
            )
            marker = self.d(
                packageName=self.package,
                resourceId="com.sina.weibo:id/titlebarTabView_hot",
            )
            home_tab = self.d(
                packageName=self.package,
                description="首页",
                clickable=True,
            )
            limit = step.get("max_back", 4)
            for count in range(limit + 1):
                current = self.d.info.get("currentPackageName")
                if current and current != self.package:
                    raise RuntimeError("Weibo left foreground")

                if marker.exists(timeout=0):
                    detail = {"back_count": count, "clicked_home": False}
                    break

                if home_tab.exists(timeout=0):
                    info = home_tab.info
                    bounds = info.get("visibleBounds") or info["bounds"]
                    left, top = bounds["left"], bounds["top"]
                    right, bottom = bounds["right"], bounds["bottom"]
                    if (
                        0 <= left < right <= width
                        and 0 <= top < bottom <= height
                        and (top + bottom) / 2 >= height * 0.85
                    ):
                        self.d.click((left + right) // 2, (top + bottom) // 2)
                        detail = {"back_count": count, "clicked_home": True}
                        break

                if count == limit:
                    raise RuntimeError("Weibo home navigation not reached")
                self.d.press("back")
                time.sleep(step.get("back_delay", 0.15))
        elif action == "back_until_home_native":
            started = time.monotonic()
            marker = self.d(
                packageName=self.package,
                resourceId=step["home_resource_id"],
            )
            limit = step.get("max_back", 5)
            count = 0
            checks = 0.0
            presses = 0.0

            while True:
                phase = time.monotonic()
                reached = marker.exists(timeout=0)
                checks += time.monotonic() - phase

                if reached:
                    break
                if count >= limit:
                    raise RuntimeError("Home not reached")

                if (
                    time.monotonic() - started
                    >= step.get("return_timeout", 4)
                ):
                    raise RuntimeError("Return home exceeded time budget")

                package = (
                    self.d.info.get("currentPackageName")
                    or self.d.app_current().get("package")
                )
                if package != self.package:
                    raise RuntimeError("App left foreground")

                phase = time.monotonic()
                self.d.press("back")
                presses += time.monotonic() - phase
                count += 1
                time.sleep(step.get("back_delay", 0.15))

            detail = {
                "back_count": count,
                "method": "native",
                "check_seconds": round(checks, 3),
                "back_seconds": round(presses, 3),
            }
        elif action == "back":
            self.d.press("back")
        elif action == "enter":
            self.d.press("enter")
        elif action == "tap_ratio":
            width, height = (
                self.cached_window_size or self.d.window_size()
            )
            x_ratio = float(step["x_ratio"])
            y_ratio = float(step["y_ratio"])
            if not (0 < x_ratio < 1 and 0 < y_ratio < 1):
                raise ValueError("Tap ratios must be between 0 and 1")
            self.d.click(
                int(width * x_ratio), int(height * y_ratio)
            )
        # elif action == "tap":
        #     self.d.click(step["x"], step["y"])
        elif action == "wait":
            time.sleep(step.get("seconds", 3))
        elif action == "expect":
            pass
        else:
            raise ValueError("Unknown action: " + action)
        if step.get("skip_post_check", False):
            return detail
        if before is not None:
            self.wait_for_page_change(before)
        if step.get("expect"):
            phase_started = time.monotonic()

            if step.get("native_expect"):
                groups = step["expect"]
                if len(groups) != 1 or len(groups[0]) != 1:
                    raise ValueError(
                        "native_expect requires exactly one selector"
                    )

                selector = groups[0][0]
                allowed = {
                    "resourceId", "text", "description", "className"
                }
                if not selector or not set(selector).issubset(allowed):
                    raise ValueError("Unsupported native_expect selector")

                control = self.d(packageName=self.package, **selector)
                if not control.exists(
                    timeout=step.get("expect_timeout", 2)
                ):
                    raise RuntimeError(
                        "Expected control not reached: %r" % selector
                    )
            else:
                if step.get("native_expect_groups"):
                    self.expect_native_groups(
                        step["expect"],
                        timeout=step.get("expect_timeout", 5),
                    )
                else:
                    self.expect(step["expect"], timeout=step.get("expect_timeout"))

            if step.get("trace_timing"):
                detail["expect_seconds"] = round(
                    time.monotonic() - phase_started, 3
                )
        elif not (
            self.profile.get("fast_mode", False) and action == "input"
        ):
            self.tree()
        return detail


def validate_profile(profile):
    if not profile.get("home"):
        raise NeedsConfiguration("Home-page selectors are required")
    if not profile.get("steps"):
        raise NeedsConfiguration("No scenario steps configured")
    for step in profile["steps"]:
        if step["action"] in {"click", "input"} and not step.get("selectors"):
            raise NeedsConfiguration("Selectors missing for " + step["name"])
        if step.get("skip_post_check") is not True:
            if step["action"] in {"click", "click_ocr", "tap", "back", "enter", "swipe_up"} and not step.get("expect"):
                raise NeedsConfiguration("Post-action checks missing for " + step["name"])


def run(device, app, out_dir=None, timeout=12.0, profile_path=None,
        hold_seconds=0.0, script_started=None, interval_seconds=0.0,
        startup_timing=None):
    """One call runs one app scenario; the caller has already restored its home."""
    started = script_started if script_started is not None else time.monotonic()
    path = Path(profile_path) if profile_path else ROOT / "profiles" / (app + ".json")
    profile = json.loads(path.read_text(encoding="utf-8"))
    base = Path(out_dir) if out_dir else ROOT / "results" / app
    folder = base.resolve() / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True, exist_ok=False)
    initialization = dict(startup_timing or {})
    phase_started = time.monotonic()
    info = device.info
    initialization["device_info"] = round(time.monotonic() - phase_started, 3)
    phase_started = time.monotonic()
    scenario = Scenario(device, profile, folder, timeout, device_info=info)
    initialization["window_size"] = round(time.monotonic() - phase_started, 3)
    result = {"app": app, "package": profile["package"], "status": "FAIL",
              "profile_validation": profile.get("validation", "UNVERIFIED"),
              "steps": [], "error": None, "output_dir": str(folder),
              "evidence_errors": scenario.evidence_errors,
              "interval_seconds": interval_seconds,
              "initialization_breakdown_seconds": initialization}
    row = None
    home_verified = False
    return_steps = []
    try:
        validate_profile(profile)
        if not math.isfinite(hold_seconds) or hold_seconds < 0:
            raise NeedsConfiguration("--time must be finite and nonnegative")
        if not math.isfinite(interval_seconds) or interval_seconds < 0:
            raise NeedsConfiguration("--interval must be finite and nonnegative")
        steps = profile["steps"]
        return_steps = []
        if steps[-1].get("name") == "return_to_home":
            return_start = len(steps) - 1
            # Keyboard dismissal may sit between the final Back operations.
            while return_start > 0:
                previous = steps[return_start - 1]
                if not (previous.get("name", "").startswith("return_to_")
                        or previous.get("action") in {
                            "back", "back_until_home", "back_until_home_native",
                            "weibo_return_home",
                        }):
                    break
                return_start -= 1
            return_steps = list(range(return_start, len(steps)))
        if hold_seconds and not return_steps:
            raise NeedsConfiguration("--time requires a final return_to_home step")
        reserve = float(profile.get("return_reserve_seconds", 2.0))
        if not math.isfinite(reserve) or reserve < 0:
            raise NeedsConfiguration("return_reserve_seconds must be finite and nonnegative")
        reserve += max(0, len(return_steps) - 1) * interval_seconds
        phase_started = time.monotonic()
        if not info.get("screenOn", False):
            raise NotAtHome("Screen is off; unlock and open the app home first")
        package = (
            info.get("currentPackageName")
            if profile.get("fast_mode", False) else None
        )
        if not package:
            package = device.app_current().get("package")
        if package != profile["package"]:
            raise NotAtHome("Expected foreground package: " + profile["package"])
        initialization["foreground_check"] = round(time.monotonic() - phase_started, 3)
        phase_started = time.monotonic()
        try:
            if profile.get("home_native", False):
                scenario.expect_native_groups(profile["home"], timeout=2)
            else:
                scenario.expect(profile["home"], timeout=2)
        except RuntimeError as exc:
            raise NotAtHome(str(exc)) from exc
        home_verified = True
        initialization["home_check"] = round(time.monotonic() - phase_started, 3)
        scenario.capture("00_home")
        result["initialization_seconds"] = round(time.monotonic() - started, 3)
        print("[%s] initialization and home check completed in %.3fs" %
              (app, result["initialization_seconds"]), flush=True)
        print("[%s] initialization: %s" % (app, ", ".join(
            "%s=%.3fs" % (name, seconds) for name, seconds in initialization.items()
        )), flush=True)
        actions_started = time.monotonic()
        for index, step in enumerate(profile["steps"], 1):
            if index > 1 and interval_seconds:
                print("[%s] interval %.3fs before %s" %
                      (app, interval_seconds, step["name"]), flush=True)
                time.sleep(interval_seconds)
            if (
                hold_seconds
                and return_steps
                and index - 1 == return_steps[0]
            ):
                remaining = max(
                    0.0,
                    started + hold_seconds - time.monotonic(),
                )
                if remaining:
                    print(
                        "[%s] video playing for %.3fs before returning"
                        % (app, remaining),
                        flush=True,
                    )
                    time.sleep(remaining)

                result["return_started_elapsed_seconds"] = round(
                    time.monotonic() - started,
                    3,
                )
            row = {"name": step["name"], "status": "RUNNING"}
            result["steps"].append(row)
            print("[%s] %02d %s" % (app, index, step["name"]), flush=True)
            step_started = time.monotonic()
            row["detail"] = scenario.execute(step)
            row["elapsed_seconds"] = round(
                time.monotonic() - step_started, 3
            )
            print(
                "[%s] %s completed in %.3fs"
                % (app, step["name"], row["elapsed_seconds"]),
                flush=True,
            )
            scenario.capture("%02d_%s" % (index, step["name"]))
            row["status"] = "PASS"
            if step["name"] == "return_to_home":
                now = time.monotonic()
                result["home_elapsed_seconds"] = round(now - started, 3)
                result["action_elapsed_seconds"] = round(
                    now - actions_started, 3
                )
                if hold_seconds:
                    result["time_budget_met"] = (
                        now - started <= hold_seconds
                    )
        result["status"] = "PASS"
    except NeedsConfiguration as exc:
        result.update(status="NEEDS_CONFIGURATION", error=str(exc))
    except NotAtHome as exc:
        result.update(status="FAIL" if home_verified else "NOT_AT_HOME", error=str(exc))
    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        if row is not None and row["status"] == "RUNNING":
            row.update(
                status="FAIL",
                error=result["error"],
            )

        if hold_seconds and "time_budget_met" not in result:
            result["time_budget_met"] = False

        if result["status"] == "PASS":
            if profile.get("capture_success", False):
                scenario.capture("final")
        else:
            scenario.capture("failure")

        # WPS中途失败时，仍依次执行末尾的返回步骤。
        if (
            app == "wps"
            and home_verified
            and result["status"] != "PASS"
            and return_steps
        ):
            recovered = False

            for step_index in return_steps:
                cleanup = profile["steps"][step_index]
                recovery = {
                    "name": "recover_" + cleanup["name"],
                    "status": "RUNNING",
                }
                result["steps"].append(recovery)

                try:
                    recovery["detail"] = scenario.execute(cleanup)
                    recovery["status"] = "PASS"

                    if cleanup["name"] == "return_to_home":
                        recovered = True
                except Exception as exc:
                    recovery.update(
                        status="FAIL",
                        error="%s: %s"
                        % (type(exc).__name__, exc),
                    )
                    continue

            scenario.capture(
                "recovery_home"
                if recovered
                else "recovery_failure"
            )

        if (
            app == "weibo"
            and home_verified
            and result["status"] != "PASS"
        ):
            cleanup = next(
                (
                    step
                    for step in profile["steps"]
                    if step.get("name") == "return_to_home"
                ),
                None,
            )

            if cleanup is not None:
                recovery = {
                    "name": "recover_to_home",
                    "status": "RUNNING",
                }
                result["steps"].append(recovery)

                try:
                    recovery["detail"] = scenario.execute(cleanup)
                    recovery["status"] = "PASS"
                    scenario.capture("recovery_home")
                except Exception as exc:
                    recovery.update(
                        status="FAIL",
                        error="%s: %s"
                        % (type(exc).__name__, exc),
                    )
                    scenario.capture("recovery_failure")

        result["elapsed_seconds"] = round(
            time.monotonic() - started,
            3,
        )

        (folder / "result.json").write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return result


def run_douyin(device, out_dir):
    path = ROOT.parent / "douyin" / "douyin.py"
    spec = importlib.util.spec_from_file_location("verified_douyin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run(device, out_dir) if out_dir else module.run(device)


def main(default_app=None):
    script_started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", default=default_app,
                        choices=["douyin"] + sorted(p.stem for p in (ROOT / "profiles").glob("*.json")),
                        required=default_app is None)
    parser.add_argument("--time", type=float, default=0.0,
                        help="Target seconds from script start until home is reached")
    parser.add_argument("--interval", type=float, default=0.0,
                        help="Extra seconds between completed scenario steps (default: 0)")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--capture", action="store_true", help="Save current UI without executing actions")
    parser.add_argument("--list", action="store_true", help="Print scenario without connecting to phone")
    args = parser.parse_args()
    if not math.isfinite(args.time) or args.time < 0:
        parser.error("--time must be finite and nonnegative")
    if not math.isfinite(args.interval) or args.interval < 0:
        parser.error("--interval must be finite and nonnegative")
    # if args.app == "douyin" and args.time:
    #     parser.error("douyin has no return_to_home step for --time")
    # if args.app == "douyin" and args.interval:
    #     parser.error("douyin uses a separate runner without --interval support")
    if args.list:
        if args.app == "douyin":
            print("Verified scenario: view 3 posts, swipe twice, dwell 3s each")
        else:
            path = args.profile or ROOT / "profiles" / (args.app + ".json")
            print(path.read_text(encoding="utf-8"))
        return 0
    try:
        import uiautomator2 as u2
        connect_started = time.monotonic()
        device = u2.connect()
        startup_timing = {
            "cli_and_import": round(connect_started - script_started, 3),
            "connect": round(time.monotonic() - connect_started, 3),
        }
        if args.capture:
            folder = ROOT / "captures" / args.app / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            folder.mkdir(parents=True)
            xml = device.dump_hierarchy(compressed=True)
            (folder / "window.xml").write_text(xml, encoding="utf-8")
            controls = [node.attrib for node in ET.fromstring(xml).iter("node")
                        if any(node.get(key) for key in ("text", "resource-id", "content-desc"))]
            (folder / "controls.json").write_text(
                json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8")
            device.screenshot(str(folder / "screen.png"))
            (folder / "info.json").write_text(json.dumps(
                device.app_current(), ensure_ascii=False, indent=2), encoding="utf-8")
            print(folder)
            return 0
        result = (run_douyin(device, args.out) if args.app == "douyin"
                  else run(device, args.app, args.out, profile_path=args.profile,
                           hold_seconds=args.time, script_started=script_started,
                           interval_seconds=args.interval,
                           startup_timing=startup_timing))
    except Exception as exc:
        print("%s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_CODES[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
