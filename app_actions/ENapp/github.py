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
        "open_search": "打开搜索",
        "input_keyword": "输入关键词",
        "submit_search": "提交搜索",
        "wait_for_results": "等待搜索结果",
        "return_right_1": "第一次向右滑动返回",
        "return_right_2": "第二次向右滑动返回",
        "return_right_3": "第三次向右滑动返回",
    }
    status_labels = {"PASS": "成功", "FAIL": "失败", "RUNNING": "执行中", "COMPLETED": "已完成"}

    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=8)
    args = parser.parse_args()

    if not all(math.isfinite(v) for v in vars(args).values()):
        parser.error("时间参数必须是有限数值，不能为无穷大或 NaN")

    if args.time < 0 or args.interval < 0 or args.timeout <= 0:
        parser.error("--time 和 --interval 必须大于或等于 0；--timeout 必须大于 0")

    base_dir = Path(__file__).resolve().parent
    config = json.loads(
        (base_dir / "profiles" / "github.json")
        .read_text(encoding="utf-8-sig")
    )

    package = config["package"]
    selectors = config["selectors"]
    gestures = config["gestures"]

    result = {
        "app": config["app"],
        "package": package,
        "keyword": config["keyword"],
        "status": "FAIL",
        "steps": [],
    }

    device = None

    def step(name, action, apply_interval=True):
        if apply_interval and result["steps"] and args.interval:
            time.sleep(args.interval)

        row = {
            "name": name,
            "status": "RUNNING",
        }
        result["steps"].append(row)

        print(
            "[github] 第 %02d 步：%s"
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
                "[github] %s %s，耗时 %.3f 秒"
                % (
                    step_labels.get(name, name),
                    status_labels.get(row["status"], row["status"]),
                    row["elapsed_seconds"],
                ),
                flush=True,
            )

    def find_unique(rules, message):
        deadline = time.monotonic() + args.timeout

        while True:
            for rule in rules:
                control = device(
                    packageName=package,
                    **rule,
                )

                if control.count == 1:
                    return control

            if time.monotonic() >= deadline:
                raise RuntimeError(message)

            time.sleep(0.15)

    def any_present(rules):
        return any(
            device(
                packageName=package,
                **rule,
            ).exists
            for rule in rules
        )

    def wait_until(check, message):
        deadline = time.monotonic() + args.timeout

        while True:
            if check():
                return

            if time.monotonic() >= deadline:
                raise RuntimeError(message)

            time.sleep(0.2)

    def open_search():
        button = find_unique(
            selectors["search_button"],
            "未找到 GitHub 搜索按钮",
        )
        button.click(timeout=1)
        search_box = find_unique(
            [
                {
                    "textMatches":
                    r"(?i)^(搜索\s*GitHub|Search\s*GitHub)$"
                },
                {
                    "descriptionMatches":
                    r"(?i)^(搜索\s*GitHub|Search\s*GitHub)$"
                },
                {
                    "className": "android.widget.EditText"
                },
            ],
            "未找到顶部搜索框",
        )
        search_box.click(timeout=1)
        return {
            "method": "search_icon_then_search_box",
        }

    def input_keyword():
        automation_packages = {
            "com.github.uiautomator",
            "com.android.adbkeyboard",
            "io.appium.settings",
        }

        current = device.current_ime()
        if current.split("/")[0] in automation_packages:
            output = device.shell(["ime", "list", "-s"]).output
            normal_imes = [
                line.strip()
                for line in output.splitlines()
                if "/" in line
                and line.strip().split("/")[0]
                not in automation_packages
            ]

            if not normal_imes:
                raise RuntimeError(
                    "未找到已启用的普通输入法"
                )

            # Prefer a configured keyboard; otherwise use the first one.
            selected = config.get("normal_ime") or normal_imes[0]
            if selected not in normal_imes:
                raise RuntimeError(
                    "配置的普通输入法未启用"
                )

            device.shell(["ime", "set", selected])
            wait_until(
                lambda: device.current_ime() == selected,
                "未能切换到普通输入法",
            )
            time.sleep(0.4)

        device.clipboard = config["keyword"]
        device.press(29, 0x1000)  
        device.press(279)       

        return {
            "method": "normal_keyboard_clipboard_paste",
            "keyboard": device.current_ime(),
            "value": config["keyword"],
            "input_verified": False,
        }

    def submit_search():
        keyword = config["keyword"]
        option = device(
            packageName=package,
            resourceId=package + ":id/title",
            text='包含 "%s" 的仓库' % keyword,
            clickable=True,
        )

        if not option.wait(timeout=2):
            raise RuntimeError(
                "未找到仓库搜索选项"
            )

        option.click(timeout=0.5)
        return {
            "method": "repository_search_control",
            "keyword": keyword,
            "search_scope": "repositories",
            "results_verified": False,
        }

    def wait_for_results():
        wait_until(
            lambda: any_present(selectors["result_marker"]),
            "未找到搜索结果标识",
        )

        print(
            "[github] 额外等待 3 秒，等待搜索结果加载",
            flush=True,
        )
        time.sleep(3.0)

        return {
            "result_marker_verified": True,
            "extra_loading_wait_seconds": 3.0,
        }

    def return_right():
        x1, y1, x2, y2 = gestures["return"]

        device.swipe(
            int(screen_width * x1),
            int(screen_height * y1),
            int(screen_width * x2),
            int(screen_height * y2),
            duration=0.2,
        )
        time.sleep(0.15)

        return {
            "direction": "left_edge_to_right",
            "swipe_count": 1,
            "home_verified": False,
        }

    try:
        connect_started = time.monotonic()
        device = u2.connect()

        result["connect_seconds"] = round(
            time.monotonic() - connect_started,
            3,
        )

        device.implicitly_wait(0)
        screen_width, screen_height = device.window_size()

        require_app_ui(device, package, timeout=args.timeout)

        result["initialization_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED,
            3,
        )

        print(
            "[github] 初始化完成，耗时 %.3f 秒"
            % result["initialization_seconds"],
            flush=True,
        )

        step("open_search", open_search)
        step("input_keyword", input_keyword)
        step("submit_search", submit_search)
        step("wait_for_results", wait_for_results)

        if args.interval:
            time.sleep(args.interval)

        remaining = max(
            0.0, SCRIPT_STARTED + args.time - time.monotonic()
        )
        result["wait_before_return_seconds"] = round(remaining, 3)
        print(
            "[github] 等待 %.3f 秒后返回" % remaining,
            flush=True,
        )
        time.sleep(remaining)

        result["return_started_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        step("return_right_1", return_right, apply_interval=False)
        step("return_right_2", return_right)
        step("return_right_3", return_right)

        result["status"] = "PASS"

    except Exception as exc:
        result["error"] = "%s: %s" % (
            type(exc).__name__,
            exc,
        )
        print(
            "[github] 失败：" + result["error"],
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
