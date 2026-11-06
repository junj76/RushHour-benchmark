import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math
from pathlib import Path

import uiautomator2 as u2
from app_ui import require_app_ui
from flow_controls import capture, wait_value, save_failure


def home_feed(screen):
    ids = {screen.rid(n) for n in screen.nodes}
    return {"main_top_app_bar_search", "bottom_nav", "feed_lazy_column"} <= ids


def first_post(screen):
    if not home_feed(screen):
        return None
    feeds = [n for n in screen.nodes if screen.rid(n) == "feed_lazy_column"]
    posts = [n for feed in feeds for n in screen.descendants(feed)
             if screen.rid(n) == "post_unit" and n.get("clickable") == "true"]
    return min(posts, key=lambda n: (screen.box(n)[1], screen.box(n)[0])) if posts else None


def detail_scroll(screen):
    if home_feed(screen):
        return None
    candidates = []
    for node in screen.nodes:
        left, top, right, bottom = screen.box(node)
        if node.get("scrollable") == "true" and bottom - top > right - left:
            candidates.append(node)

    roots = [n for n in candidates if not any(
        n is not other and n in list(other.iter()) for other in candidates)]
    if len(roots) > 1:
        raise RuntimeError("详情页有多个独立纵向滚动容器，需要详情页 XML")
    return roots[0] if roots else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    if not all(math.isfinite(v) for v in vars(args).values()) or (
        args.time < 0 or args.interval < 0 or args.timeout <= 0
    ):
        parser.error("时间参数必须有限；time/interval >= 0，timeout > 0")
    config = json.loads((Path(__file__).resolve().parent / "profiles/reddit.json")
                        .read_text(encoding="utf-8-sig"))
    package = config["package"]
    result = {"app": "reddit", "package": package, "status": "FAIL", "steps": [],
              "verification": "action_execution_only"}
    device = None

    def step(name, action):
        row = {"name": name, "status": "FAIL"}
        result["steps"].append(row)
        started = time.monotonic()
        try:
            row["detail"] = action()
            row["status"] = "PASS"
        except Exception as exc:
            row["error"] = str(exc)
            raise
        finally:
            row["elapsed_seconds"] = round(time.monotonic() - started, 3)
            print("[reddit] %s %s in %.3fs" %
                  (name, row["status"], row["elapsed_seconds"]), flush=True)

    try:
        device = u2.connect()
        device.implicitly_wait(0)
        require_app_ui(device, package, timeout=args.timeout)

        def find_post():
            screen = capture(device, package)
            node = first_post(screen)
            return (screen, node) if node is not None else None

        def locate_detail():
            screen = capture(device, package)
            node = detail_scroll(screen)
            return (screen, node) if node is not None else None

        def open_post():
            screen, post = wait_value(find_post, args.timeout, "首页第一篇帖子未出现")
            description = screen.label(post)
            screen.element(device, post).click()
            wait_value(locate_detail, args.timeout, "未离开首页或未出现详情滚动容器")
            return {"method": "first_home_post_unit_control", "description": description,
                    "home_left_verified": True, "detail_scroll_container_verified": True,
                    "post_content_verified": False}

        def browse_down():
            screen, container = wait_value(locate_detail, args.timeout, "帖子滚动容器未出现")
            before = screen.fingerprint(container)
            screen.element(device, container).swipe("up", scale=0.75)
            time.sleep(max(args.interval, 0.4))
            after, target = wait_value(locate_detail, args.timeout, "滑动后详情滚动容器未出现")
            return {"method": "post_scroll_control_swipe_up", "swipe_count": 1,
                    "content_layout_changed": before != after.fingerprint(target),
                    "scroll_verified": False}

        def return_home():
            deadline = time.monotonic() + args.timeout
            back_count = 0

            def is_home():
                return home_feed(capture(device, package))

            def success():
                return {
                    "method": "android_back" if back_count else "already_home",
                    "back_count": back_count,
                    "home_verified": True,
                }

            for _ in range(2):
                if is_home():
                    return success()

                require_app_ui(device, package, timeout=1)

                # 检测期间页面可能已完成切换，再检查一次。
                if is_home():
                    return success()
                if time.monotonic() >= deadline:
                    break

                device.press("back")
                back_count += 1

                # 等待返回动画，未到首页时才考虑下一次返回。
                check_until = min(deadline, time.monotonic() + 2)
                while time.monotonic() < check_until:
                    if is_home():
                        return success()
                    time.sleep(0.15)

            while time.monotonic() < deadline:
                if is_home():
                    return success()
                time.sleep(0.15)

            raise RuntimeError(
                "已返回 %d 次，仍未检测到首页；请提供失败 XML"
                % back_count
            )

        step("open_first_post", open_post)
        step("browse_down_1", browse_down)
        step("browse_down_2", browse_down)
        remaining = max(0, SCRIPT_STARTED + args.time - time.monotonic())
        result["wait_before_return_seconds"] = round(remaining, 3)
        print("[reddit] 等待 %.3f 秒后返回" % remaining, flush=True)
        time.sleep(remaining)
        result["return_started_elapsed_seconds"] = round(time.monotonic() - SCRIPT_STARTED, 3)
        step("return_home", return_home)
        result["status"] = "COMPLETED"
    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        save_failure(device, "reddit", result)
    result["elapsed_seconds"] = round(time.monotonic() - SCRIPT_STARTED, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
