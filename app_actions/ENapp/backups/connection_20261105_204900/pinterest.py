import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math
from pathlib import Path
import re

import uiautomator2 as u2
from app_ui import require_app_ui
from flow_controls import capture, pinterest_pair, pin_identity, wait_value, save_failure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    if not all(math.isfinite(v) for v in vars(args).values()) or (
        args.time < 0 or args.interval < 0 or args.timeout <= 0
    ):
        parser.error("Invalid time parameters")
    cfg = json.loads((Path(__file__).resolve().parent / "profiles/pinterest.json")
                     .read_text(encoding="utf-8-sig"))
    package = cfg["package"]
    result = {"app": "pinterest", "package": package, "status": "FAIL", "steps": []}
    device = None

    def step(name, action):
        item = {"name": name, "status": "FAIL"}
        result["steps"].append(item)
        started = time.monotonic()
        try:
            item["detail"] = action()
            item["status"] = "PASS"
            return item["detail"]
        except Exception as exc:
            item["error"] = str(exc)
            raise
        finally:
            item["elapsed_seconds"] = round(time.monotonic() - started, 3)
            print("[pinterest] %s %s in %.3fs" %
                  (name, item["status"], item["elapsed_seconds"]), flush=True)

    try:
        device = u2.connect()
        device.implicitly_wait(0)
        require_app_ui(device, package, timeout=args.timeout)

        def feed():
            screen = capture(device, package)
            pair = pinterest_pair(screen)
            return (screen, pair) if pair else None

        baseline, initial = wait_value(feed, args.timeout, "Two-column pin feed not detected")
        identities = [pin_identity(baseline, n) for n in initial]
        grid_ids = {baseline.rid(n) for n in baseline.nodes if baseline.rid(n) in {
            "pin_grid", "pin_grid_recycler_view", "home_feed", "home_feed_recycler_view"}}
        if not any(identities) and not (baseline.home_selected() and grid_ids):
            raise RuntimeError("Feed has no identifiable pin labels or Home/grid marker; XML required")

        def same_feed():
            value = feed()
            if value is None:
                return None
            screen, pair = value
            current = {pin_identity(screen, n) for n in pair}
            labelled = [identity for identity in identities if identity]
            identity_match = bool(labelled) and all(identity in current for identity in labelled)
            ids = {screen.rid(n) for n in screen.nodes}
            grid_match = bool(grid_ids & ids) and screen.home_selected()
            return value if identity_match or grid_match else None

        def open_pin(side):
            screen, pair = wait_value(same_feed, args.timeout, "Original pin feed not restored")
            screen.element(device, pair[side]).click()
            wait_value(lambda: not same_feed(), args.timeout, "Click did not leave the pin feed")
            return {"method": "pin_image_control", "side": "left" if side == 0 else "right",
                    "feed_left_verified": True, "detail_page_verified": False}

        def back_to_feed():
            screen = capture(device, package)
            buttons = screen.unique_actions(n for n in screen.nodes if (
                screen.rid(n) in {"closeup_back", "closeup_back_button", "pin_closeup_back"}
                or re.fullmatch(r"(?i)(Back|Navigate up|返回|向上导航)", screen.label(n))))
            if len(buttons) == 1:
                screen.element(device, buttons[0]).click()
                method = "back_control"
            else:
                device.press("back")
                method = "android_back"
            wait_value(same_feed, args.timeout, "Back did not restore the original two-column feed")
            return {"method": method, "home_verified": True, "original_feed_verified": True}

        step("open_top_left_pin", lambda: open_pin(0))
        time.sleep(cfg["first_view_seconds"])
        step("return_to_feed_1", back_to_feed)
        step("open_top_right_pin", lambda: open_pin(1))
        time.sleep(max(0, SCRIPT_STARTED + args.time - time.monotonic()))
        step("return_to_feed_2", back_to_feed)
        result["status"] = "PASS"
    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        save_failure(device, "pinterest", result)
    result["elapsed_seconds"] = round(time.monotonic() - SCRIPT_STARTED, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
