import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math
from pathlib import Path
import re

import uiautomator2 as u2
from uiautomator2.exceptions import XPathElementNotFoundError
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

        def skip_phone_setup():
            screen = capture(device, package)
            if not any(screen.rid(n) == "activity_nux_carousel" for n in screen.nodes):
                return {"skipped": False}
            if not any(re.search(r"电话号码|phone number", screen.label(n), re.I)
                       for n in screen.nodes):
                return {"skipped": False}
            buttons = screen.unique_actions(n for n in screen.nodes
                                            if re.fullmatch(r"跳过|Skip", screen.label(n), re.I))
            if len(buttons) != 1:
                raise RuntimeError("手机号引导页未找到唯一的跳过按钮")
            screen.element(device, buttons[0]).click()
            wait_value(lambda: not any(
                re.search(r"你的电话号码是|What.*phone number", s.label(n), re.I)
                for s in [capture(device, package)] for n in s.nodes
            ), args.timeout, "点击跳过后仍停留在手机号引导页")
            return {"skipped": True, "method": "skip_phone_button"}

        step("skip_phone_setup", skip_phone_setup)

        def confirm_country_setup():
            screen = capture(device, package)
            if not any(screen.rid(n) == "country_list_action" for n in screen.nodes):
                return {"skipped": True}
            country = next((screen.label(n) for n in screen.nodes
                            if screen.rid(n) == "list_action_header"), "")
            # 保留页面当前国家/地区，只确认下一步，不修改账号地区。
            button = device(resourceId=package + ":id/country_next_button")
            button.click(timeout=args.timeout)
            wait_value(lambda: not device(resourceId=package + ":id/country_list_action").exists,
                       args.timeout, "确认国家/地区后页面未切换")
            return {"country": country, "method": "country_next_button"}

        step("confirm_country_setup", confirm_country_setup)

        def select_interests_setup():
            screen = capture(device, package)
            if not any("选择 3 项" in screen.label(n) for n in screen.nodes):
                return {"skipped": True}

            def next_buttons(s):
                return s.unique_actions(n for n in s.nodes if s.label(n) == "下一步")

            chosen = []

            def available_interest():
                s = capture(device, package)
                if next_buttons(s):
                    return s, None
                # 兴趣卡片的无障碍说明形如“摄影 3 / 29”。每次点击后重新取页面。
                topics = [n for n in s.nodes if re.fullmatch(
                    r".+\s+\d+\s*/\s*\d+", n.get("content-desc", ""))
                    and n.get("content-desc") not in chosen and not s.selected(n)]
                target = next((n for n in topics if s.clickable(n) is not None), None)
                return (s, target) if target is not None else None

            for _ in range(3):
                screen, target = wait_value(available_interest, args.timeout,
                                            "等待兴趣卡片加载超时，请检查网络及失败 XML")
                if target is None:
                    break
                chosen.append(target.get("content-desc"))
                screen.element(device, screen.clickable(target)).click()
                time.sleep(max(args.interval, 0.3))

            def ready():
                s = capture(device, package)
                buttons = next_buttons(s)
                return (s, buttons[0]) if len(buttons) == 1 else None

            screen, button = wait_value(ready, args.timeout, "选择兴趣后下一步按钮未启用")
            screen.element(device, button).click()
            wait_value(lambda: not device(resourceId=package + ":id/activity_nux_carousel").exists,
                       args.timeout, "选择兴趣后仍未离开引导页")
            return {"selected_interests": chosen, "method": "interest_cards_then_next"}

        step("select_interests_setup", select_interests_setup)

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
            def click_current_pin():
                value = same_feed()
                if value is None:
                    return False
                screen, pair = value
                try:
                    # 页面异步加载会改变绝对路径，失效后重新抓取，避免沿用旧路径等待 20 秒。
                    device.xpath(screen.path(pair[side])).click(timeout=0.5)
                    return True
                except XPathElementNotFoundError:
                    return False

            wait_value(click_current_pin, args.timeout, "首页卡片持续更新，未能点击目标卡片")
            wait_value(lambda: not same_feed(), args.timeout, "Click did not leave the pin feed")
            return {"method": "pin_image_control", "side": "left" if side == 0 else "right",
                    "feed_left_verified": True, "detail_page_verified": False}

        def back_to_feed():
            methods = []
            for attempt in range(2):
                if same_feed():
                    return {"methods": methods, "back_count": len(methods),
                            "home_verified": True, "original_feed_verified": True}
                screen = capture(device, package)
                buttons = screen.unique_actions(n for n in screen.nodes if (
                    screen.rid(n) in {"closeup_back", "closeup_back_button", "pin_closeup_back"}
                    or re.fullmatch(r"(?i)(Back|Navigate up|返回|向上导航)", screen.label(n))))
                if len(buttons) == 1:
                    screen.element(device, buttons[0]).click()
                    methods.append("back_control")
                else:
                    device.press("back")
                    methods.append("android_back")
                try:
                    wait_value(same_feed, min(args.timeout, 2.0) if attempt == 0 else args.timeout,
                               "Back did not restore the original two-column feed")
                    return {"methods": methods, "back_count": len(methods),
                            "home_verified": True, "original_feed_verified": True}
                except RuntimeError:
                    screen = capture(device, package)
                    still_detail = any(screen.rid(n) == "fragment_pin" for n in screen.nodes)
                    if attempt == 1 or not still_detail:
                        raise

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
