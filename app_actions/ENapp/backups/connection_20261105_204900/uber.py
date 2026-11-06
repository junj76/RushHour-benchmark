import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import uiautomator2 as u2
from app_ui import require_app_ui


def main():
    step_labels = {
        "input_keyword": "输入关键词",
        "open_destination": "打开目的地输入页",
        "return_1": "第一次返回",
        "return_2": "第二次返回",
        "return_3": "第三次返回",
        "choose_first_suggestion": "选择第一条地点建议",
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
        (Path(__file__).resolve().parent / "profiles" / "uber.json")
        .read_text(encoding="utf-8-sig")
    )
    package = config["package"]
    result = {
        "app": "uber",
        "package": package,
        "status": "FAIL",
        "steps": [],
    }

    def wait(check, message):
        deadline = time.monotonic() + args.timeout
        while True:
            value = check()
            if value:
                return value
            if time.monotonic() >= deadline:
                raise RuntimeError(message)
            time.sleep(0.15)

    def step(name, action, interval=True):
        if interval and result["steps"] and args.interval:
            time.sleep(args.interval)

        row = {"name": name, "status": "RUNNING"}
        result["steps"].append(row)
        print(
            "[uber] 第 %02d 步：%s" % (len(result["steps"]), step_labels.get(name, name)),
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
                "[uber] %s %s，耗时 %.3f 秒"
                % (step_labels.get(name, name), status_labels.get(row["status"], row["status"]), row["elapsed_seconds"]),
                flush=True,
            )

    try:
        started = time.monotonic()
        d = u2.connect()
        result["connect_seconds"] = round(
            time.monotonic() - started, 3
        )
        d.implicitly_wait(0)

        require_app_ui(d, package, timeout=args.timeout)

        def home_ready():
            tree = ET.fromstring(
                d.dump_hierarchy(compressed=False)
            )
            nodes = [
                n for n in tree.iter("node")
                if n.get("package") == package
            ]
            ids = {n.get("resource-id", "") for n in nodes}

            return (
                any(
                    n.get("content-desc") == config["home_prompt"]
                    for n in nodes
                )
                and any(
                    n.get("text") == config["home_label"]
                    for n in nodes
                )
                and package + ":id/location_editor_bottom_sheet_view"
                not in ids
                and package + ":id/ub__text_search_v2_scroll_view"
                not in ids
            )

        def open_destination():
            label = json.dumps(
                config["home_prompt"], ensure_ascii=False
            )
            entry = d.xpath(
                f"//*[@package='{package}'"
                f" and @content-desc={label}]"
                "/ancestor-or-self::*[@clickable='true'][1]"
            )
            entry.click(timeout=args.timeout)

            field = d.xpath(
                f"//*[@resource-id='{package}:id/"
                "ub__location_edit_search_container_destination']"
                f"//*[@resource-id='{package}:id/edit_text']"
            )
            if not field.wait(timeout=args.timeout):
                raise RuntimeError("目的地输入框未出现")

            return {"method": "home_destination_control"}

        def input_keyword():
            field = d(
                packageName=package,
                resourceId=package + ":id/edit_text",
            )
            if field.count != 1:
                raise RuntimeError(
                    "目的地输入框不存在或匹配不唯一"
                )

            field.click(timeout=0.5)
            field.set_text(config["keyword"])
            wait(
                lambda: field.get_text() == config["keyword"],
                "输入内容校验失败",
            )
            return {
                "method": "input_control",
                "value": config["keyword"],
            }

        def choose_first_suggestion():
            # Match place rows with both a name and an address.
            # Excludes the "search in another city" option.
            rows = d.xpath(
                f"//*[@resource-id='{package}:id/"
                "ub__text_search_v2_scroll_view']"
                "//android.widget.Button[@clickable='true']"
                "[count(.//android.widget.TextView) >= 2]"
            )
            matches = wait(
                lambda: rows.all(),
                "地点建议列表未出现",
            )
            description = matches[0].attrib.get(
                "content-desc", ""
            )
            if not description:
                raise RuntimeError(
                    "第一条建议没有无障碍描述"
                )

            target = d(
                packageName=package,
                className="android.widget.Button",
                description=description,
                clickable=True,
            )
            if target.count != 1:
                raise RuntimeError(
                    "第一条建议不存在或匹配不唯一"
                )

            target.click(timeout=0.5)
            return {
                "method": "first_place_suggestion_control",
                "selected_place": description,
                "destination_page_verified": False,
            }

        def search_page_visible():
            field = d.xpath(
                f"//*[@package='{package}'"
                f" and @resource-id='{package}:id/"
                "ub__location_edit_search_container_destination']"
                f"//*[@resource-id='{package}:id/edit_text']"
            )
            return bool(field.exists)

        def back():
            require_app_ui(d, package, timeout=args.timeout)

            if home_ready():
                return {
                    "method": "already_home",
                    "back_sent": False,
                    "home_verified": True,
                }

            count = result.get("actual_return_count", 0)

            # 第一次从目的地页面返回；后续只允许在搜索页返回。
            if count > 0 and not search_page_visible():
                raise RuntimeError(
                    "当前既不是已识别的首页，也不是搜索页，"
                    "停止继续返回，需要当前页面 XML"
                )

            d.press("back")
            result["actual_return_count"] = count + 1
            time.sleep(0.35)

            stop = time.monotonic() + args.timeout
            while True:
                if home_ready():
                    result["home_elapsed_seconds"] = round(
                        time.monotonic() - SCRIPT_STARTED, 3
                    )
                    return {
                        "method": "android_back",
                        "home_verified": True,
                    }

                if search_page_visible():
                    return {
                        "method": "android_back",
                        "search_page_verified": True,
                        "home_verified": False,
                    }

                if time.monotonic() >= stop:
                    raise RuntimeError(
                        "返回后的页面无法识别，停止继续返回"
                    )
                time.sleep(0.2)

        wait(home_ready, "请从 Uber 首页开始运行")

        result["initialization_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(
            "[uber] 初始化完成，耗时 %.3f 秒"
            % result["initialization_seconds"],
            flush=True,
        )

        step("open_destination", open_destination)
        step("input_keyword", input_keyword)
        step("choose_first_suggestion", choose_first_suggestion)

        if args.interval:
            time.sleep(args.interval)

        remaining = max(
            0.0, SCRIPT_STARTED + args.time - time.monotonic()
        )
        result["wait_before_return_seconds"] = round(remaining, 3)
        print(
            "[uber] 等待 %.3f 秒后返回" % remaining,
            flush=True,
        )
        time.sleep(remaining)

        result["return_started_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        # 等待地点选择后的页面切换完成。
        # time.sleep(1.0)

        for index in range(1, 4):
            step(f"return_{index}", back, interval=False)

            if result["steps"][-1]["detail"]["home_verified"]:
                break

        if not home_ready():
            raise RuntimeError("最多返回三次后，仍未识别到首页")

        result["status"] = "PASS"

    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        print("[uber] 失败：" + result["error"], flush=True)
    finally:
        result["elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
