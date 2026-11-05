import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math
from pathlib import Path

import uiautomator2 as u2
from app_ui import require_app_ui
from flow_controls import capture, shorts_tab, shorts_viewer, shorts_content, wait_value, save_failure, ensure_youtube_home


def scheduled_swipes(device, package, started, total_seconds, rows,
                     clock=time.monotonic, sleep=time.sleep):
    deadline = started + total_seconds
    last_swipe = None
    for index, offset in enumerate((3.0, 6.0), 1):
        target_time = started + offset
        # if last_swipe is not None:
        #     target_time = max(target_time, last_swipe + 3.0)
        if target_time >= deadline or clock() >= deadline:
            break
        # sleep(max(0, target_time - clock()))
        row = {"name": "scroll_next_short_%d" % index, "status": "FAIL"}
        rows.append(row)
        action_started = clock()
        try:
            screen = capture(device, package)
            viewer = shorts_viewer(screen)
            if viewer is None:
                raise RuntimeError("Shorts 容器未出现")

            before = shorts_content(screen)
            element = screen.element(device, viewer)

            # 提前完成控件定位，按固定时间等待。
            sleep(max(0, target_time - clock()))

            if clock() >= deadline:
                rows.pop()
                break

            last_swipe = clock()
            element.swipe("up", scale=0.65)
            row.update(status="PASS", detail={
                "method": "shorts_viewer_control_swipe_up",
                "scheduled_elapsed_seconds": offset,
                "actual_started_elapsed_seconds": round(last_swipe - started, 3),
                "video_change_verified": False, "playback_verified": False})
            if clock() < deadline:
                after = capture(device, package)
                if shorts_viewer(after) is None:
                    raise RuntimeError("滑动后离开了 Shorts 页面")
                content = shorts_content(after)
                row["detail"]["video_change_verified"] = bool(before and content and before != content)
        except Exception as exc:
            row.update(status="FAIL", error=str(exc))
            raise
        finally:
            row["elapsed_seconds"] = round(clock() - action_started, 3)
        print("[youtube_shorts] %s %s at %.3fs" %
              (row["name"], row["status"], last_swipe - started), flush=True)
    sleep(max(0, deadline - clock()))
    return rows


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
    config = json.loads((Path(__file__).resolve().parent / "profiles/youtube_shorts.json")
                        .read_text(encoding="utf-8-sig"))
    package = config["package"]
    result = {"app": "youtube_shorts", "package": package, "status": "FAIL", "steps": [],
              "verification": "gesture_execution_only"}
    device = None
    try:
        device = u2.connect()
        device.implicitly_wait(0)
        require_app_ui(device, package, timeout=args.timeout)
        result["home_preparation"] = ensure_youtube_home(device, package, args.timeout)

        def find_tab():
            screen = capture(device, package)
            tab = shorts_tab(screen)
            return (screen, tab) if tab is not None else None

        screen, tab = wait_value(find_tab, args.timeout, "未找到底部 Shorts 导航按钮")
        if not screen.home_selected():
            raise RuntimeError("请先打开 YouTube 首页")
        row = {"name": "open_shorts", "status": "FAIL"}
        result["steps"].append(row)
        action_started = time.monotonic()
        try:
            screen.element(device, tab).click()
            wait_value(lambda: shorts_viewer(capture(device, package)) is not None,
                       args.timeout, "Shorts 容器未出现")
            row.update(status="PASS", detail={"method": "shorts_bottom_tab_control",
                                              "shorts_viewer_verified": True})
        except Exception as exc:
            row["error"] = str(exc)
            raise
        finally:
            row["elapsed_seconds"] = round(time.monotonic() - action_started, 3)
        result["initialization_seconds"] = round(time.monotonic() - SCRIPT_STARTED, 3)
        shorts_started = time.monotonic()
        scheduled_swipes(
            device, package, shorts_started,
            args.time, result["steps"],
        )
        result["swipe_count"] = sum(row["status"] == "PASS" for row in result["steps"]
                                    if row["name"].startswith("scroll_next_short_"))
        result["return_home"] = ensure_youtube_home(device, package, args.timeout)
        result["status"] = "COMPLETED"
    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        save_failure(device, "youtube_shorts", result)
    result["elapsed_seconds"] = round(time.monotonic() - SCRIPT_STARTED, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
