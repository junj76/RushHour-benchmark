import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math
import re
from pathlib import Path
import xml.etree.ElementTree as ET

import uiautomator2 as u2
from app_ui import require_app_ui
from flow_controls import save_failure, wait_value


BASE_DIR = Path(__file__).resolve().parent


def main():

    step_labels = {
        "open_search": "打开搜索",
        "input_keyword": "输入关键词",
        "submit_search": "提交搜索",
        "browse_up": "向上浏览",
        "return_right_1": "第一次向右滑动返回",
    }

    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()

    if not all(
        math.isfinite(v)
        for v in (args.time, args.interval, args.timeout)
    ):
        parser.error("时间参数必须是有限数值，不能为无穷大或 NaN")

    if args.time < 0 or args.interval < 0 or args.timeout <= 0:
        parser.error("--time 和 --interval 必须大于或等于 0；--timeout 必须大于 0")

    config_path = (
        BASE_DIR / "profiles" / (Path(__file__).stem + ".json")
    )
    config = json.loads(
        config_path.read_text(encoding="utf-8-sig")
    )

    package = config["package"]
    keyword = config["keyword"]
    selectors = config["selectors"]
    gestures = config["gestures"]

    result = {
        "app": config["app"],
        "package": package,
        "keyword": keyword,
        "status": "FAIL",
        "steps": [],
    }

    d = None
    row = None
    step_started = None
    screen_size = None

    def present(rules):
        return any(
            d(packageName=package, **rule).exists
            for rule in rules
        )

    def wait_for(rules):
        deadline = time.monotonic() + args.timeout
        while True:
            if present(rules):
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "未找到预期控件："
                    + json.dumps(rules, ensure_ascii=False)
                )
            time.sleep(0.2)

    def unique_control(rules):
        deadline = time.monotonic() + args.timeout
        while True:
            for rule in rules:
                control = d(packageName=package, **rule)
                if control.count == 1:
                    return control

            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "控件不存在或匹配不唯一："
                    + json.dumps(rules, ensure_ascii=False)
                )
            time.sleep(0.2)

    def swipe(ratios):
        width, height = screen_size

        d.swipe(
            int(width * ratios[0]),
            int(height * ratios[1]),
            int(width * ratios[2]),
            int(height * ratios[3]),
            duration=gestures["duration"],
        )
        time.sleep(gestures["settle_seconds"])

    def first_result():
        tree = ET.fromstring(
            d.dump_hierarchy(compressed=True)
        )
        width, height = screen_size
        candidates = []

        for node in tree.iter("node"):
            if node.get("package") != package:
                continue

            text = (
                node.get("text", "").strip()
                or node.get("content-desc", "").strip()
            )

            if not text.startswith(keyword):
                continue

            if len(text) > 80:
                continue

            resource_id = node.get("resource-id", "")
            if "omnibox" in resource_id:
                continue

            box = re.fullmatch(
                r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",
                node.get("bounds", ""),
            )
            if not box:
                continue

            x1, y1, x2, y2 = map(int, box.groups())
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(width, x2), min(height, y2)

            if x2 <= x1 or y2 <= y1:
                continue

            center_y = (y1 + y2) / 2

            if not height * 0.46 < center_y < height * 0.90:
                continue

            candidates.append(
                (y1, x1, text, (x1, y1, x2, y2))
            )

        if not candidates:
            return None

        return min(candidates, key=lambda item: (item[0], item[1]))

    def open_search():
        unique_control(selectors["search_entry"]).click()
        wait_for(selectors["search_input"])

    def input_keyword():
        field = unique_control(selectors["search_input"])
        field.click()
        field.set_text(keyword)

        deadline = time.monotonic() + args.timeout
        while field.get_text() != keyword:
            if time.monotonic() >= deadline:
                raise RuntimeError("搜索输入内容校验失败")
            time.sleep(0.2)

        return {"value": keyword}

    def place_ready():
        if d(resourceId=package + ":id/search_list_layout").exists:
            return False
        title = d.xpath(
            f"//*[@package='{package}' and @text={json.dumps(keyword, ensure_ascii=False)}]"
            "[not(ancestor::*[@resource-id='com.google.android.apps.maps:id/search_omnibox_text_box'])]"
        )
        return bool(title.exists) and (present(selectors["place_ready"]) or (
            d(packageName=package, descriptionMatches="(?i)(路线|Directions)").exists
            and d(packageName=package, descriptionMatches="(?i)(保存|Save)").exists))

    def home_ready():
        return (present(selectors["home"])
                and not d(resourceId=package + ":id/search_list_layout").exists
                and not d(resourceId=package + ":id/search_omnibox_text_clear").exists)

    def restore_home():
        backs = 0
        for _ in range(2):
            if home_ready():
                return backs
            if not (d(resourceId=package + ":id/search_list_layout").exists
                    or d(resourceId=package + ":id/search_omnibox_text_clear").exists):
                break
            d.press("back")
            backs += 1
            try:
                wait_value(home_ready, min(args.timeout, 2), "地图首页尚未恢复")
                return backs
            except RuntimeError:
                pass
        wait_value(home_ready, args.timeout, "地图首页未恢复，请检查失败 XML")
        return backs

    def submit_search():
        text_literal = json.dumps(keyword, ensure_ascii=False)
        suggestion = d.xpath(
            "//*[@resource-id="
            "'com.google.android.apps.maps:id/typed_suggest_container']"
            "/*[@clickable='true']"
            f"[.//*[@text={text_literal}]]"
        )
        if suggestion.wait(timeout=min(args.timeout, 3)):
            suggestion.click(timeout=0.5)
            method = "search_suggestion_xpath"
        else:
            # 网络建议可能不出现，直接提交已校验的搜索文字。
            d.press("enter")
            method = "enter_key"
        cards = d.xpath(
            f"//*[@resource-id='{package}:id/search_list_layout']"
            "//android.view.ViewGroup[@clickable='true']"
            "[.//*[@content-desc='路线' or @content-desc='Directions']]"
            "[.//*[@content-desc='保存' or @content-desc='Save']]"
        )
        wait_value(lambda: place_ready() or cards.exists, args.timeout,
                   "未出现地点结果列表或详情页")
        if not place_ready():
            cards.all()[0].click()
            method += "_then_first_result_card"
        wait_value(place_ready, args.timeout, "点击结果卡片后未进入目标地点详情")
        time.sleep(gestures["settle_seconds"])

        return {
            "method": method,
            "search_results_verified": True,
        }   

    def browse_up():
        swipe([0.5, 0.90, 0.5, 0.55])
        return {
            "direction": "finger_up",
            "swipe_count": 1,
            "scroll_verified": False,
        }

    def first_return():
        swipe(gestures["swipe_right"])
        extra_backs = restore_home()

        result["home_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        return {
            "direction": "right",
            "swipe_count": 1,
            "home_verified": True,
            "extra_back_count": extra_backs,
        }

    try:
        connect_started = time.monotonic()
        d = u2.connect()
        result["connect_seconds"] = round(
            time.monotonic() - connect_started, 3
        )

        require_app_ui(d, package, timeout=args.timeout)
        d.implicitly_wait(0)

        screen_size = d.window_size()
        result["initial_back_count"] = restore_home()

        result["initialization_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(
            "[gmap] 初始化完成，耗时 %.3f 秒"
            % result["initialization_seconds"],
            flush=True,
        )

        steps = [
            ("open_search", open_search),
            ("input_keyword", input_keyword),
            ("submit_search", submit_search),
            ("browse_up", browse_up),
            ("return_right_1", first_return),
        ]

        for index, (name, action) in enumerate(steps, 1):
            if index > 1 and args.interval:
                time.sleep(args.interval)

            if name == "return_right_1":
                remaining = max(
                    0.0,
                    SCRIPT_STARTED + args.time - time.monotonic(),
                )
                result["wait_before_return_seconds"] = round(
                    remaining, 3
                )

                if remaining:
                    print(
                        "[gmap] 等待 %.3f 秒后返回"
                        % remaining,
                        flush=True,
                    )
                    time.sleep(remaining)

                result["return_started_elapsed_seconds"] = round(
                    time.monotonic() - SCRIPT_STARTED, 3
                )

            row = {"name": name, "status": "RUNNING"}
            result["steps"].append(row)

            print("[gmap] 第 %02d 步：%s" % (index, step_labels.get(name, name)), flush=True)

            step_started = time.monotonic()
            detail = action()

            row.update(
                status="PASS",
                elapsed_seconds=round(
                    time.monotonic() - step_started, 3
                ),
            )
            if detail is not None:
                row["detail"] = detail

            print(
                "[gmap] %s 已完成，耗时 %.3f 秒"
                % (step_labels.get(name, name), row["elapsed_seconds"]),
                flush=True,
            )
            step_started = None

        result["status"] = "PASS"

    except Exception as exc:
        error = "%s: %s" % (type(exc).__name__, exc)
        result["error"] = error
        save_failure(d, "gmap", result)

        if row is not None and row["status"] == "RUNNING":
            row.update(status="FAIL", error=error)
            if step_started is not None:
                row["elapsed_seconds"] = round(
                    time.monotonic() - step_started, 3
                )
            print(
                "[gmap] %s 失败，耗时 %.3f 秒: %s"
                % (step_labels.get(row["name"], row["name"]), row.get("elapsed_seconds", 0), error),
                flush=True,
            )

    finally:
        result["elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
