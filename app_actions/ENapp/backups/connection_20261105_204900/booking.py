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
        "return_to_home": "返回首页",
        "open_destination": "打开目的地输入页",
        "input_destination": "输入目的地",
        "choose_city": "选择城市",
        "confirm_dates": "确认日期",
        "search": "搜索",
        "wait_for_results": "等待搜索结果",
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

    config = json.loads(
        (Path(__file__).resolve().parent / "profiles" / "booking.json")
        .read_text(encoding="utf-8-sig")
    )
    package = config["package"]
    result = {
        "app": "booking",
        "package": package,
        "status": "FAIL",
        "steps": [],
    }

    def step(name, action, interval=True):
        if interval and result["steps"] and args.interval:
            time.sleep(args.interval)

        row = {"name": name, "status": "RUNNING"}
        result["steps"].append(row)
        print(
            "[booking] 第 %02d 步：%s" % (len(result["steps"]), step_labels.get(name, name)),
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
                "[booking] %s %s，耗时 %.3f 秒"
                % (step_labels.get(name, name), status_labels.get(row["status"], row["status"]), row["elapsed_seconds"]),
                flush=True,
            )

    def wait(check, message):
        deadline = time.monotonic() + args.timeout
        while True:
            value = check()
            if value:
                return value
            if time.monotonic() >= deadline:
                raise RuntimeError(message)
            time.sleep(0.15)

    try:
        started = time.monotonic()
        device = u2.connect()
        result["connect_seconds"] = round(
            time.monotonic() - started, 3
        )
        device.implicitly_wait(0)

        require_app_ui(device, package, timeout=args.timeout)

        def by_id(key):
            return device.xpath(
                f"//*[@package='{package}'"
                f" and @resource-id='{config[key]}']"
            )

        def click_unique(target, message):
            matches = wait(lambda: target.all(), message)
            if len(matches) != 1:
                raise RuntimeError("匹配到多个控件：" + message)
            matches[0].click()

        def home_ready():
            return (
                bool(by_id("destination_id").exists)
                and bool(by_id("search_id").exists)
                and not bool(by_id("date_confirm_id").exists)
                and not bool(by_id("results_id").exists)
            )

        def open_destination():
            click_unique(
                by_id("destination_id"),
                "未找到首页的目的地控件",
            )
            field = device(
                packageName=package,
                className="android.widget.EditText",
            )
            if not field.wait(timeout=args.timeout):
                raise RuntimeError("目的地输入框未出现")
            return {"method": "destination_control"}

        def input_destination():
            field = device(
                packageName=package,
                className="android.widget.EditText",
            )
            if field.count != 1:
                raise RuntimeError("目的地输入框不唯一")
            field.click(timeout=0.5)
            field.set_text(config["keyword"])
            wait(
                lambda: field.get_text() == config["keyword"],
                "目的地输入内容校验失败",
            )
            return {"value": config["keyword"]}

        def choose_city():
            device.press("enter")

            dates = by_id("date_confirm_id")
            if dates.wait(timeout=0.8):
                return {
                    "method": "enter_key",
                    "date_picker_verified": True,
                }
            city = device(
                packageName=package,
                className="android.widget.TextView",
                text=config["keyword"],
            )

            if not city.wait(timeout=args.timeout):
                raise RuntimeError("未找到城市建议项")
            if city.count != 1:
                raise RuntimeError("匹配到多个城市建议项")

            city.click(timeout=0.5)

            wait(
                lambda: bool(dates.exists),
                "选择城市后，日期选择器未出现",
            )
            return {
                "method": "city_text_control",
                "date_picker_verified": True,
            }

        def confirm_dates():
            button = device(
                packageName=package,
                resourceId=config["date_confirm_id"],
                enabled=True,
            )
            if not button.wait(timeout=args.timeout):
                raise RuntimeError("日期确认按钮不可用")
            button.click(timeout=0.5)
            wait(home_ready, "首页搜索表单未重新出现")
            return {"method": "confirm_current_dates"}

        def search():
            click_unique(
                by_id("search_id"),
                "未找到首页搜索按钮",
            )
            return {"method": "home_search_control"}

        def wait_for_results():
            cards = device.xpath(
                f"//*[@resource-id='{config['results_id']}']"
                "/android.view.View"
                "[@clickable='true'"
                " and string-length(@content-desc)>0]"
            )

            wait(
                lambda: bool(cards.exists),
                "住宿搜索结果卡片未出现",
            )
            return {"accommodation_cards_verified": True}

        def return_home():
            device.press("back")
            time.sleep(config["return_settle_seconds"])
            wait(home_ready, "按一次返回键后，未回到首页")
            result["home_elapsed_seconds"] = round(
                time.monotonic() - SCRIPT_STARTED, 3
            )
            return {
                "method": "android_back",
                "back_count": 1,
                "home_verified": True,
            }

        wait(home_ready, "请从 Booking 首页开始运行")
        result["initialization_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(
            "[booking] 初始化完成，耗时 %.3f 秒"
            % result["initialization_seconds"],
            flush=True,
        )

        step("open_destination", open_destination)
        step("input_destination", input_destination)
        step("choose_city", choose_city)
        step("confirm_dates", confirm_dates)
        step("search", search)
        step("wait_for_results", wait_for_results)

        if args.interval:
            time.sleep(args.interval)
        remaining = max(
            0.0, SCRIPT_STARTED + args.time - time.monotonic()
        )
        result["wait_before_return_seconds"] = round(remaining, 3)
        print(
            "[booking] 等待 %.3f 秒后返回" % remaining,
            flush=True,
        )
        time.sleep(remaining)

        result["return_started_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        step("return_to_home", return_home, interval=False)
        result["status"] = "PASS"

    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        print("[booking] 失败：" + result["error"], flush=True)
    finally:
        result["elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
