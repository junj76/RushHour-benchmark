import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math
from pathlib import Path

from device_connection import connect_device
from app_ui import require_app_ui


def main():

    step_labels = {
        "scroll_next_video_1": "第一次滑动到下一个视频",
        "scroll_next_video_2": "第二次滑动到下一个视频",
    }
    status_labels = {"PASS": "成功", "FAIL": "失败", "RUNNING": "执行中", "COMPLETED": "已完成"}

    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args()

    if not all(math.isfinite(v) for v in vars(args).values()):
        parser.error("时间参数必须是有限数值，不能为无穷大或 NaN")

    if args.time < 0 or args.interval < 0 or args.timeout <= 0:
        parser.error("--time 和 --interval 必须大于或等于 0；--timeout 必须大于 0")

    base_dir = Path(__file__).resolve().parent
    profile_path = base_dir / "profiles" / "tiktok.json"
    config = json.loads(
        profile_path.read_text(encoding="utf-8-sig")
    )

    package = config["package"]
    gestures = config["gestures"]
    result = {
        "app": config["app"],
        "package": package,
        "status": "FAIL",
        "verification": "gesture_execution_only",
        "steps": [],
    }

    deadline = SCRIPT_STARTED + args.time
    device = None

    def run_step(name, action, apply_interval=True):
        if apply_interval and result["steps"] and args.interval:
            time.sleep(args.interval)

        row = {
            "name": name,
            "status": "RUNNING",
        }
        result["steps"].append(row)

        print(
            "[tiktok] 第 %02d 步：%s"
            % (len(result["steps"]), step_labels.get(name, name)),
            flush=True,
        )

        started = time.monotonic()

        try:
            row["detail"] = action()
            row["status"] = "PASS"
        except Exception as exc:
            row.update(
                status="FAIL",
                error="%s: %s" % (type(exc).__name__, exc),
            )
            raise
        finally:
            row["elapsed_seconds"] = round(
                time.monotonic() - started,
                3,
            )
            print(
                "[tiktok] %s %s，耗时 %.3f 秒"
                % (
                    step_labels.get(name, name),
                    status_labels.get(row["status"], row["status"]),
                    row["elapsed_seconds"],
                ),
                flush=True,
            )

    def find_feed():
        controls = device(
            packageName=package,
            scrollable=True,
        )

        if controls.count == 0:
            raise RuntimeError(
                "未找到可滚动的 TikTok 内容流控件"
            )

        candidates = []

        for index in range(controls.count):
            item = controls[index]
            info = item.info
            bounds = (
                info.get("visibleBounds")
                or info.get("bounds")
            )

            if not bounds:
                continue

            width = bounds["right"] - bounds["left"]
            height = bounds["bottom"] - bounds["top"]

            if width > 0 and height > 0:
                candidates.append(
                    (width * height, item)
                )

        if not candidates:
            raise RuntimeError(
                "TikTok 滚动控件没有可见边界"
            )

        return max(
            candidates,
            key=lambda item: item[0],
        )[1]

    def scroll_next_video():
        feed = find_feed()

        feed.swipe(
            "up",
            steps=gestures["scroll_steps"],
        )

        time.sleep(
            gestures["settle_seconds"]
        )

        return {
            "method": "native_scrollable_control",
            "direction": "up",
            "scroll_verified": False,
        }

    try:
        connect_started = time.monotonic()
        device = connect_device()

        result["connect_seconds"] = round(
            time.monotonic() - connect_started,
            3,
        )

        device.implicitly_wait(0)

        allowed_packages = config.get("packages", [config["package"]])
        package = require_app_ui(device, allowed_packages, timeout=args.timeout)
        result["package"] = package

        result["initialization_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED,
            3,
        )

        print(
            "[tiktok] 初始化完成，耗时 %.3f 秒"
            % result["initialization_seconds"],
            flush=True,
        )

        # 第一次上滑，浏览下一条视频。
        run_step(
            "scroll_next_video_1",
            scroll_next_video,
        )

        # 第一次滑动后观看 2 秒。
        remaining = max(
            0.0,
            deadline - time.monotonic(),
        )
        watch_seconds = min(
            gestures["watch_seconds"],
            remaining,
        )

        result["first_watch_seconds"] = round(
            watch_seconds,
            2,
        )

        print(
            "[tiktok] 继续观看 %.3f 秒"
            % watch_seconds,
            flush=True,
        )

        time.sleep(watch_seconds)

        # 如果时间还没到，再滑动一次。
        remaining = deadline - time.monotonic()

        if remaining > 0:
            run_step(
                "scroll_next_video_2",
                scroll_next_video,
                apply_interval=False,
            )

        # 第二次滑动后一直停留到总时间结束。
        remaining = max(
            0.0,
            deadline - time.monotonic(),
        )

        result["wait_before_finish_seconds"] = round(
            remaining,
            3,
        )

        if remaining:
            print(
                "[tiktok] 等待 %.3f 秒后到达设定时间"
                % remaining,
                flush=True,
            )
            time.sleep(remaining)

        result["time_reached_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED,
            3,
        )
        result["time_budget_met"] = (
            result["time_reached_elapsed_seconds"]
            >= args.time
        )
        result["status"] = "PASS"

    except Exception as exc:
        result["error"] = "%s: %s" % (
            type(exc).__name__,
            exc,
        )
        print(
            "[tiktok] 失败：" + result["error"],
            flush=True,
        )

    finally:
        result["elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED,
            3,
        )
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )
        )

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
