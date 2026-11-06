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
        "return_to_home": "返回首页",
        "browse_down_1": "第一次向下浏览",
        "browse_down_2": "第二次向下浏览",
        "browse_down_3": "第三次向下浏览",
        "open_chart": "打开排行榜",
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

    config = json.loads(
        (Path(__file__).resolve().parent / "profiles" / "spotify.json")
        .read_text(encoding="utf-8-sig")
    )
    package = config["package"]
    gestures = config["gestures"]

    result = {
        "app": "spotify",
        "package": package,
        "status": "FAIL",
        "verification": "action_execution_only",
        "steps": [],
    }

    def step(name, action, apply_interval=True):
        if apply_interval and result["steps"] and args.interval:
            time.sleep(args.interval)

        row = {"name": name, "status": "RUNNING"}
        result["steps"].append(row)
        print(
            "[spotify] 第 %02d 步：%s" % (len(result["steps"]), step_labels.get(name, name)),
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
                time.monotonic() - started, 3
            )
            print(
                "[spotify] %s %s，耗时 %.3f 秒"
                % (step_labels.get(name, name), status_labels.get(row["status"], row["status"]), row["elapsed_seconds"]),
                flush=True,
            )

    try:
        started = time.monotonic()
        device = connect_device()
        result["connect_seconds"] = round(
            time.monotonic() - started, 3
        )
        device.implicitly_wait(0)

        require_app_ui(device, package, timeout=args.timeout)

        width, height = device.window_size()

        def open_chart():
            conditions = []
            for title in config["section_titles"]:
                value = json.dumps(title, ensure_ascii=False)
                conditions.append(
                    f"@text={value} or @content-desc={value}"
                )
            title_condition = " or ".join(conditions)

            cards = device.xpath(
                f"//*[@package='{package}'"
                f" and @resource-id='{package}:id/heading_container']"
                f"[.//*[{title_condition}]]"
                "/following-sibling::*"
                f"[@resource-id='{package}:id/carousel'][1]"
                "//*"
                f"[@resource-id='{package}:id/card_root'"
                " and @clickable='true'"
                " and @enabled='true']"
            )

            deadline = time.monotonic() + args.timeout

            while True:
                matches = cards.all()

                if matches:
                    target = matches[0]
                    label = target.attrib.get("content-desc", "")
                    target.click()
                    time.sleep(gestures["open_wait_seconds"])

                    return {
                        "method": "first_card_in_charts_section",
                        "visible_card_count": len(matches),
                        "selected_label": label,
                        "detail_page_verified": False,
                    }

                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "排行榜区域中未找到可见卡片"
                    )
                time.sleep(0.15)

        def browse_down():
            x1, y1, x2, y2 = gestures["browse"]

            device.swipe(
                int(width * x1),
                int(height * y1),
                int(width * x2),
                int(height * y2),
                duration=gestures["duration"],
            )
            time.sleep(gestures["settle_seconds"])
            return {
                "direction": "finger_up",
                "swipe_count": 1,
                "scroll_verified": False,
            }

        def return_home():
            device.press("back")
            time.sleep(gestures["settle_seconds"])
            return {
                "method": "android_back",
                "back_count": 1,
                "home_verified": False,
            }

        result["initialization_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(
            "[spotify] 初始化完成，耗时 %.3f 秒"
            % result["initialization_seconds"],
            flush=True,
        )

        step("open_chart", open_chart)
        step("browse_down_1", browse_down)
        step("browse_down_2", browse_down)
        # step("browse_down_3", browse_down)

        if args.interval:
            time.sleep(args.interval)

        remaining = max(
            0.0, SCRIPT_STARTED + args.time - time.monotonic()
        )
        result["wait_before_return_seconds"] = round(remaining, 3)
        print(
            "[spotify] 等待 %.3f 秒后返回" % remaining,
            flush=True,
        )
        time.sleep(remaining)

        result["return_started_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        step("return_to_home", return_home, apply_interval=False)
        result["status"] = "COMPLETED"

    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        print("[spotify] 失败：" + result["error"], flush=True)
    finally:
        result["elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
