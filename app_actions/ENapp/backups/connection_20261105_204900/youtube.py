import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import uiautomator2 as u2


BASE_DIR = Path(__file__).resolve().parent


class BrowseDeadline(RuntimeError):
    pass


class Page:
    def __init__(self, xml, config):
        self.config = config
        root = ET.fromstring(xml)
        self.parents = {child: parent for parent in root.iter() for child in parent}
        self.nodes = []
        for node in root.iter("node"):
            if node.get("package") != config["package"]:
                continue
            current = node
            while current is not None and current.get("visible-to-user") != "false":
                current = self.parents.get(current)
            if current is not None:
                continue
            values = re.findall(r"-?\d+", node.get("bounds", ""))
            if len(values) != 4:
                continue
            left, top, right, bottom = map(int, values)
            if right > left and bottom > top:
                self.nodes.append(node)
        self.ids = {node.get("resource-id") for node in self.nodes}

    def miniplayer(self):
        return bool(self.ids.intersection(
            self.config["miniplayer_ids"] + self.config["close_miniplayer_ids"]))

    def player(self):
        return bool(self.ids.intersection(self.config["player_ids"])) and not self.miniplayer()

    def home(self):
        if self.config["home_feed_id"] not in self.ids or self.player():
            return False
        navs = [node for node in self.nodes
                if node.get("resource-id") == self.config["home_nav_id"]]
        for nav in navs:
            for node in nav.iter("node"):
                label = node.get("content-desc", "").strip() or node.get("text", "").strip()
                if not re.fullmatch(r"(?i)(Home|\u9996\u9875|\u4e3b\u9875)(?:[,\uff0c ].*)?", label):
                    continue
                current = node
                while current is not None and current is not nav:
                    if current.get("selected") == "true" or current.get("checked") == "true":
                        return True
                    current = self.parents.get(current)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    if not all(math.isfinite(value) for value in vars(args).values()) or (
        args.time < 0 or args.interval < 0 or args.timeout <= 0
    ):
        parser.error("Finite times required: time/interval >= 0; timeout > 0")
    config = json.loads((BASE_DIR / "profiles/youtube.json").read_text(encoding="utf-8-sig"))
    result = {"app": "youtube", "package": config["package"], "status": "FAIL", "steps": []}
    labels = {"open_first_video": "\u6253\u5f00\u9996\u9875\u7b2c\u4e00\u4e2a\u6761\u76ee",
              "return_to_home": "\u8fd4\u56de\u9996\u9875",
              "close_miniplayer": "\u5173\u95ed\u5c0f\u7a97"}
    deadline = SCRIPT_STARTED + args.time
    device = None
    opened = False
    click_sent = False
    errors = []

    def elapsed():
        return round(time.monotonic() - SCRIPT_STARTED, 3)

    def check_time():
        if time.monotonic() >= deadline:
            raise BrowseDeadline("Browse deadline reached; switching to return")

    def capture():
        return Page(device.dump_hierarchy(compressed=False), config)

    def wait(check, message, browsing=False):
        stop = time.monotonic() + args.timeout
        if browsing:
            stop = min(stop, deadline)
        while True:
            if browsing:
                check_time()
            value = check()
            if value:
                return value
            if browsing:
                check_time()
            remaining = stop - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(message)
            time.sleep(min(max(args.interval, 0.1), remaining))

    def step(name, action):
        row = {"name": name, "status": "FAIL"}
        result["steps"].append(row)
        started = time.monotonic()
        try:
            row["detail"] = action() or {}
            row["status"] = "PASS"
        except BrowseDeadline as exc:
            row.update(status="DEADLINE", error=str(exc))
            raise
        except Exception as exc:
            row["error"] = str(exc)
            raise
        finally:
            row["elapsed_seconds"] = round(time.monotonic() - started, 3)
            print("[youtube] %s %s in %.3fs" % (
                labels[name], row["status"], row["elapsed_seconds"]), flush=True)

    def open_first_video():
        nonlocal click_sent, opened
        check_time()
        # The supplied XML only exposes unlabeled direct children of the feed.
        target = device.xpath(config["first_home_item_xpath"])
        wait(lambda: target.exists, "First home feed item did not appear", browsing=True)
        check_time()
        element = target.get(timeout=min(0.2, max(0.01, deadline - time.monotonic())))
        check_time()
        result["video_click_started_elapsed_seconds"] = elapsed()
        click_sent = True
        element.click()
        wait(lambda: capture().player(), "Click did not open a known video player", browsing=True)
        opened = True
        result["video_opened_elapsed_seconds"] = elapsed()
        return {"method": "first_home_feed_item_control",
                "xpath": config["first_home_item_xpath"],
                "player_page_verified": True, "playback_verified": False,
                "feed_item_video_identity_verified": False}

    def return_home():
        page = capture()
        if not page.home():
            if not page.nodes:
                raise RuntimeError("YouTube UI absent; no Back sent to another app")
            result["back_sent_elapsed_seconds"] = elapsed()
            device.press("back")
            result["actual_return_count"] = 1
            wait(lambda: capture().home(), "One Back did not restore the home feed; no extra Back sent")
        result["home_elapsed_seconds"] = elapsed()
        result["home_verified"] = True
        return {"method": "android_back" if result["actual_return_count"] else "already_home",
                "back_count": result["actual_return_count"], "home_verified": True}

    def close_miniplayer():
        page = capture()
        if not page.home():
            raise RuntimeError("Home feed not verified; refusing unrelated close controls")
        if not page.miniplayer():
            # Verify a second snapshot so a delayed miniplayer is not silently ignored.
            time.sleep(max(args.interval, 0.25))
            page = capture()
            if page.home() and not page.miniplayer():
                result["home_clean_elapsed_seconds"] = elapsed()
                return {"method": "already_absent", "known_miniplayer_absent": True,
                        "home_verified": True}

        def find_close():
            current = capture()
            if not current.home():
                raise RuntimeError("Home feed disappeared while finding the miniplayer close button")
            matches = [node for node in current.nodes
                       if node.get("resource-id") in config["close_miniplayer_ids"]
                       and node.get("enabled") != "false"]
            if len(matches) > 1:
                raise RuntimeError("Multiple miniplayer close buttons")
            return matches[0].get("resource-id") if matches else None

        close_id = wait(find_close, "Miniplayer visible but its close control was not found")
        device(packageName=config["package"], resourceId=close_id).click(timeout=0.2)
        def clean_home():
            current = capture()
            return current.home() and not current.miniplayer()
        wait(clean_home, "Miniplayer still visible or home verification failed")
        result["home_clean_elapsed_seconds"] = elapsed()
        return {"method": "miniplayer_close_control", "known_miniplayer_absent": True,
                "home_verified": True}

    try:
        started = time.monotonic()
        device = u2.connect()
        result["connect_seconds"] = round(time.monotonic() - started, 3)
        device.implicitly_wait(0)
        wait(lambda: capture().home(), "Start on the YouTube home feed", browsing=True)
        if capture().miniplayer():
            raise RuntimeError("Close the existing miniplayer before starting")
        result["initialization_seconds"] = elapsed()
        step("open_first_video", open_first_video)
    except BrowseDeadline as exc:
        result["browse_deadline_reached"] = True
        errors.append(str(exc))
    except Exception as exc:
        errors.append("%s: %s" % (type(exc).__name__, exc))
    finally:
        result["actual_return_count"] = 0
        if device is not None:
            try:
                remaining = max(0, deadline - time.monotonic())
                result["wait_before_return_seconds"] = round(remaining, 3)
                time.sleep(remaining)
                result["return_started_elapsed_seconds"] = elapsed()
                result["return_lateness_seconds"] = round(max(0, time.monotonic() - deadline), 3)
                # Return also runs after an interrupted or failed opening attempt.
                step("return_to_home", return_home)
                step("close_miniplayer", close_miniplayer)
            except Exception as exc:
                errors.append("%s: %s" % (type(exc).__name__, exc))
        if opened and not errors:
            result["status"] = "PASS"
        elif not opened and not errors:
            errors.append("Video opening was not verified")
        result["video_click_sent"] = click_sent
        if errors:
            result["error"] = "; ".join(errors)
            if device is not None:
                try:
                    folder = BASE_DIR / "ui_dumps"
                    folder.mkdir(exist_ok=True)
                    path = folder / ("youtube_failure_%d.xml" % time.time_ns())
                    path.write_text(device.dump_hierarchy(compressed=False), encoding="utf-8")
                    result["failure_xml"] = str(path)
                except Exception as exc:
                    result["failure_xml_error"] = str(exc)
        result["elapsed_seconds"] = elapsed()
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
