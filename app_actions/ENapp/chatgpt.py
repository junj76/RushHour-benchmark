import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math
from pathlib import Path

import uiautomator2 as u2
from app_ui import require_app_ui


def main():

    step_labels = {
        "input_prompt": "输入提问内容",
        "send_prompt": "发送提问",
        "read_response": "阅读回复",
        "tap_bottom_center": "点击消息输入框",
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
        (Path(__file__).resolve().parent / "profiles" / "chatgpt.json")
        .read_text(encoding="utf-8-sig")
    )
    package = config["package"]
    gestures = config["gestures"]
    result = {
        "app": "chatgpt",
        "package": package,
        "status": "FAIL",
        "steps": [],
    }

    def step(name, action, interval=True):
        if interval and result["steps"] and args.interval:
            time.sleep(args.interval)
        row = {"name": name, "status": "RUNNING"}
        result["steps"].append(row)
        print("[chatgpt] 第 %02d 步：%s" % (len(result["steps"]), step_labels.get(name, name)),
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
            print("[chatgpt] %s %s，耗时 %.3f 秒" % (
                step_labels.get(name, name), status_labels.get(row["status"], row["status"]), row["elapsed_seconds"]
            ), flush=True)

    try:
        started = time.monotonic()
        d = u2.connect()
        result["connect_seconds"] = round(
            time.monotonic() - started, 3
        )
        d.implicitly_wait(0)

        require_app_ui(d, package, timeout=args.timeout)
        width, height = d.window_size()

        def input_prompt():
            field = d(
                packageName=package,
                className="android.widget.EditText",
            )
            if not field.wait(timeout=args.timeout):
                raise RuntimeError("未找到消息输入框")
            if field.count != 1:
                raise RuntimeError("匹配到多个消息输入框")
            field.click()
            field.set_text(config["prompt"])
            if field.get_text() != config["prompt"]:
                raise RuntimeError("输入内容校验失败")
            return {"method": "input_control", "value": config["prompt"]}

        def send_prompt():
            stop = time.monotonic() + args.timeout
            while True:
                button = d(
                    packageName=package,
                    descriptionMatches=config["send_pattern"],
                    enabled=True,
                )
                if button.count == 1:
                    button.click(timeout=0.5)
                    return {
                        "method": "send_control",
                        "response_verified": False,
                    }
                if time.monotonic() >= stop:
                    raise RuntimeError(
                        "未找到发送箭头，需要提供当前页面的界面层级 XML"
                    )
                time.sleep(0.15)

        def read_response():
            time.sleep(gestures["response_wait"])
            x1, y1, x2, y2 = gestures["read_swipe"]
            d.swipe(
                int(width * x1), int(height * y1),
                int(width * x2), int(height * y2),
                duration=gestures["swipe_duration"],
            )
            return {"swipe_count": 1, "scroll_verified": False}

        def final_tap():
            field = d(
                packageName=package,
                className="android.widget.EditText",
            )
            if not field.wait(timeout=args.timeout):
                raise RuntimeError("未找到消息输入框")
            if field.count != 1:
                raise RuntimeError("匹配到多个消息输入框")

            field.click(timeout=0.5)
            return {"method": "input_control_click"}

        result["initialization_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print("[chatgpt] 初始化完成，耗时 %.3f 秒"
              % result["initialization_seconds"], flush=True)

        step("input_prompt", input_prompt)
        step("send_prompt", send_prompt)
        step("read_response", read_response)

        if args.interval:
            time.sleep(args.interval)
        remaining = max(
            0.0, SCRIPT_STARTED + args.time - time.monotonic()
        )
        result["wait_before_final_seconds"] = round(remaining, 3)
        print("[chatgpt] 等待 %.3f 秒后执行最后一次点击"
              % remaining, flush=True)
        time.sleep(remaining)

        result["final_started_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        step("tap_bottom_center", final_tap, interval=False)
        result["status"] = "COMPLETED"

    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        print("[chatgpt] 失败：" + result["error"], flush=True)
    finally:
        result["elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
