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
        "open_search": "打开搜索",
        "input_keyword": "输入关键词",
        "submit_search": "提交搜索",
        "return_to_home": "返回首页",
        "browse_down_1": "第一次向下浏览",
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
        (Path(__file__).resolve().parent / "profiles" / "google.json")
        .read_text(encoding="utf-8-sig")
    )
    package = config["package"]
    gestures = config["gestures"]
    result = {
        "app": "google",
        "package": package,
        "status": "FAIL",
        "verification": "action_execution_only",
        "steps": [],
    }

    def step(name, action, interval=True):
        if interval and result["steps"] and args.interval:
            time.sleep(args.interval)

        row = {"name": name, "status": "RUNNING"}
        result["steps"].append(row)
        print("[google] 第 %02d 步：%s" % (len(result["steps"]), step_labels.get(name, name)),
              flush=True)
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
            print("[google] %s %s，耗时 %.3f 秒" % (
                step_labels.get(name, name), status_labels.get(row["status"], row["status"]), row["elapsed_seconds"]
            ), flush=True)

    try:
        started = time.monotonic()
        d = connect_device()
        result["connect_seconds"] = round(
            time.monotonic() - started, 3
        )
        d.implicitly_wait(0)

        require_app_ui(d, package, timeout=args.timeout)

        width, height = d.window_size()

        def open_search():
            label = config["search_label"]
            targets = d.xpath(
                f"//*[@package='{package}']"
                f"[@text='{label}' or @content-desc='{label}']"
                "/ancestor-or-self::*[@clickable='true'][1]"
            )
            stop = time.monotonic() + args.timeout

            while True:
                matches = targets.all()
                if matches:
                    target = min(
                        matches,
                        key=lambda item: item.bounds[1],
                    )
                    target.click()
                    break

                if time.monotonic() >= stop:
                    raise RuntimeError(
                        "未找到首页搜索框"
                    )
                time.sleep(0.15)

            fields = d(
                packageName=package,
                className="android.widget.EditText",
            )
            if not fields.wait(timeout=args.timeout):
                raise RuntimeError(
                    "搜索输入框未出现"
                )

            return {"method": "home_search_box_control"}

        def input_keyword():
            fields = d(
                packageName=package,
                className="android.widget.EditText",
            )
            focused = d(
                packageName=package,
                className="android.widget.EditText",
                focused=True,
            )
            if focused.count == 1:
                field = focused
            elif fields.count == 1:
                field = fields
            else:
                raise RuntimeError("搜索输入框不存在或匹配不唯一")

            field.click()
            field.set_text(config["keyword"])
            if field.get_text() != config["keyword"]:
                raise RuntimeError("搜索输入内容校验失败")
            return {"value": config["keyword"]}

        def submit_search():
            d.press("enter")
            time.sleep(gestures["results_wait"])
            return {
                "method": "enter_key",
                "results_verified": False,
            }

        def swipe(ratios):
            x1, y1, x2, y2 = ratios
            d.swipe(
                int(width * x1), int(height * y1),
                int(width * x2), int(height * y2),
                duration=gestures["duration"],
            )
            time.sleep(gestures["settle_seconds"])

        def browse_down():
            swipe(gestures["browse"])
            return {
                "direction": "finger_up",
                "scroll_verified": False,
            }

        def return_home():
            d.press("back")
            time.sleep(0.8)

            home = d(
                packageName=package,
                text="搜索",
            )

            return {
                "method": "android_back",
                "home_verified": bool(home.exists),
            }

        result["initialization_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print("[google] 初始化完成，耗时 %.3f 秒"
              % result["initialization_seconds"], flush=True)
        step("open_search", open_search)
        step("input_keyword", input_keyword)
        step("submit_search", submit_search)
        step("browse_down_1", browse_down)
        # step("browse_down_2", browse_down)

        if args.interval:
            time.sleep(args.interval)
        remaining = max(
            0.0, SCRIPT_STARTED + args.time - time.monotonic()
        )
        result["wait_before_return_seconds"] = round(remaining, 3)
        print("[google] 等待 %.3f 秒后返回"
              % remaining, flush=True)
        time.sleep(remaining)

        result["return_started_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        step("return_to_home", return_home, interval=False)
        result["status"] = "COMPLETED"

    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        print("[google] 失败：" + result["error"], flush=True)
    finally:
        result["elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
