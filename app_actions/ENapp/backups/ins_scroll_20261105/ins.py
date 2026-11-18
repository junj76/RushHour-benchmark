import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math
from pathlib import Path

from device_connection import connect_device
from app_ui import require_app_ui
from flow_controls import capture, instagram_feed, like_instagram_post, wait_value, save_failure


BASE_DIR = Path(__file__).resolve().parent


def main():

    step_labels = {
        "browse_down_1": "第一次向下浏览",
        "browse_down_2": "第二次向下浏览",
        # "browse_down_3": "第三次向下浏览",
        "browse_up_1": "第一次向上浏览",
        "browse_up_2": "第二次向上浏览",
        # "browse_up_3": "第三次向上浏览",
    }

    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()

    values = (args.time, args.interval, args.timeout)
    if not all(math.isfinite(v) for v in values):
        parser.error("时间参数必须是有限数值，不能为无穷大或 NaN")
    if args.time < 0 or args.interval < 0 or args.timeout <= 0:
        parser.error("--time 和 --interval 必须大于或等于 0；--timeout 必须大于 0")

    config = json.loads(
        (BASE_DIR / "profiles" / "ins.json")
        .read_text(encoding="utf-8-sig")
    )
    package = config["package"]
    gestures = config["gestures"]

    result = {
        "app": "ins",
        "package": package,
        "status": "FAIL",
        "verification": "gesture_execution_only",
        "steps": [],
    }

    d = None
    row = None
    step_started = None

    try:
        imports_seconds = time.monotonic() - SCRIPT_STARTED

        connect_started = time.monotonic()
        d = connect_device()
        d.implicitly_wait(0)
        result["connect_seconds"] = round(
            time.monotonic() - connect_started, 3
        )

        def locate_feed():
            def find():
                screen = capture(d, package)
                feed = instagram_feed(
                    screen,
                    config["selectors"]["feed"].get("resourceId"),
                )
                return (screen, feed) if feed is not None else None

            return wait_value(
                find, args.timeout,
                "未找到包含帖子的首页纵向内容流",
            )

        check_started = time.monotonic()
        locate_feed()
        result["feed_check_seconds"] = round(
            time.monotonic() - check_started, 3
        )
        result["imports_seconds"] = round(imports_seconds, 3)

        print(
            "[ins] 导入 %.3fs，连接 %.3fs，内容流检查 %.3fs"
            % (
                result["imports_seconds"],
                result["connect_seconds"],
                result["feed_check_seconds"],
            ),
            flush=True,
        )

        # def like_post():
        #     return like_instagram_post(
        #         d, package, args.timeout, gestures["settle_seconds"],
        #         configured_id=config["selectors"]["feed"].get("resourceId"),
        #     )

        # def swipe(key):
        #     screen, feed = locate_feed()
        #     before = screen.fingerprint(feed)

        #     target = d(
        #         packageName=package,
        #         resourceId="android:id/list",
        #         scrollable=True,
        #     )
        #     if target.count != 1:
        #         raise RuntimeError("未找到唯一的首页内容列表")

        #     if key == "browse_down":
        #         reported = target.scroll.vert.forward(steps=30)
        #     elif key == "browse_up":
        #         reported = target.scroll.vert.backward(steps=30)
        #     else:
        #         raise ValueError("未知滑动方向：" + key)

        #     time.sleep(max(gestures["settle_seconds"], 0.1))

        #     after, new_feed = locate_feed()
        #     changed = before != after.fingerprint(new_feed)

            # if not changed and not reported:
            #     raise RuntimeError(
            #         "列表未报告滚动成功，且布局未变化；"
            #         "可能已到边界或滚动未生效"
            #     )

            # return {
            #     "method": "native_feed_list_scroll",
            #     "action": key,
            #     "android_reported_success": bool(reported),
            #     "content_layout_changed": changed,
            #     "scroll_verified": False,
            # }
        def swipe(key):
            target = d(
                packageName=package,
                resourceId="android:id/list",
                scrollable=True,
            )

            if target.count != 1:
                raise RuntimeError("未找到唯一的首页内容列表")

            if key == "browse_down":
                reported = target.scroll.vert.forward(steps=50)
            elif key == "browse_up":
                reported = target.scroll.vert.backward(steps=50)
            else:
                raise ValueError("未知滑动方向：" + key)

            time.sleep(0.1)

            return {
                "method": "native_feed_list_scroll",
                "action": key,
                "android_reported_success": bool(reported),
                "content_layout_changed": None,
                "scroll_verified": False,
            }

        result["initialization_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(
            "[ins] 初始化完成，耗时 %.3f 秒"
            % result["initialization_seconds"],
            flush=True,
        )

        steps = [
            ("browse_down_1", lambda: swipe("browse_down")),
            ("browse_down_2", lambda: swipe("browse_down")),
            # ("browse_down_3", lambda: swipe("browse_down")),
            ("browse_up_1", lambda: swipe("browse_up")),
            ("browse_up_2", lambda: swipe("browse_up")),
            # ("browse_up_3", lambda: swipe("browse_up")),
        ]

        for index, (name, action) in enumerate(steps, 1):
            if index > 1 and args.interval:
                time.sleep(args.interval)

            if name == "browse_up_1":
                remaining = max(
                    0.0,
                    SCRIPT_STARTED + args.time - time.monotonic(),
                )
                result["wait_before_return_seconds"] = round(
                    remaining, 3
                )

                if remaining:
                    print(
                        "[ins] 等待 %.3f 秒后向上滑动返回"
                        % remaining,
                        flush=True,
                    )
                    time.sleep(remaining)

                result["return_started_elapsed_seconds"] = round(
                    time.monotonic() - SCRIPT_STARTED, 3
                )

            row = {"name": name, "status": "RUNNING"}
            result["steps"].append(row)

            print("[ins] 第 %02d 步：%s" % (index, step_labels.get(name, name)), flush=True)

            step_started = time.monotonic()
            detail = action()

            row.update(
                status="PASS",
                elapsed_seconds=round(
                    time.monotonic() - step_started, 3
                ),
                detail=detail,
            )

            print(
                "[ins] %s 已完成，耗时 %.3f 秒"
                % (step_labels.get(name, name), row["elapsed_seconds"]),
                flush=True,
            )
            step_started = None

        result["status"] = "PASS"

    except Exception as exc:
        error = "%s: %s" % (type(exc).__name__, exc)
        result["error"] = error
        save_failure(d, "ins", result)

        if row is not None and row["status"] == "RUNNING":
            row.update(
                status="FAIL",
                error=error,
                elapsed_seconds=round(
                    time.monotonic() - step_started, 3
                ),
            )
            print(
                "[ins] %s 失败，耗时 %.3f 秒: %s"
                % (step_labels.get(row["name"], row["name"]), row["elapsed_seconds"], error),
                flush=True,
            )
        else:
            print("[ins] 失败：" + error, flush=True)

    finally:
        result["elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
