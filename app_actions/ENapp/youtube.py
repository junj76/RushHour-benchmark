import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import uiautomator2 as u2
from app_ui import require_app_ui
from flow_controls import ensure_youtube_home, save_failure

# BASE_DIR = ENapp 路径
BASE_DIR = Path(__file__).resolve().parent

def main():
    step_labels = {
        "open_search": "打开搜索",
        "input_keyword": "输入关键词",
        "submit_search": "提交搜索",
        "open_first_video": "打开第一个视频",
        "return_to_results": "返回搜索结果页",
        "return_to_home": "返回首页",
        "close_miniplayer": "关闭小窗",
    }

    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    # 等待多久返回    每个步骤时间间隔    超时时间
    values = (args.time, args.interval, args.timeout)
    if not all(math.isfinite(value) for value in values):
        parser.error("时间必须是有限的数值")
    if args.time < 0 or args.interval < 0 or args.timeout <= 0:
        parser.error("--time 和 --interval 必须大于或等于 0；--timeout 必须大于 0")

    config = json.loads(
        (BASE_DIR / "profiles" / "youtube.json")
        .read_text(encoding="utf-8-sig")
    )
    package = config["package"]
    selectors = config["selectors"]
    app = config["app"]
    result = {
        "app": app,
        "package": package,
        "keyword": config["keyword"],
        "status": "FAIL",
        "steps": [],
    }

    d = None
    row = None
    step_started = None

    # 检查某组选择器是否能找到控件
    def present(rules):
        return any(
            d(packageName=package, **rule).exists
            for rule in rules
        )

    # 循环检查，直到满足条件或超时
    def wait_until(check, message):
        deadline = time.monotonic() + args.timeout
        while True:
            if check():
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(message)
            time.sleep(0.2)

    # 寻找唯一控件，必要时选最靠上的匹配项
    def find_control(rules, first=False):
        deadline = time.monotonic() + args.timeout

        while True:
            for rule in rules:
                control = d(packageName=package, **rule)
                count = control.count

                if count == 1:
                    return control

                if count > 1 and first:
                    matches = []
                    for index in range(count):
                        item = control[index]
                        info = item.info
                        box = info.get("visibleBounds") or info["bounds"]
                        if (
                            box["right"] > box["left"]
                            and box["bottom"] > box["top"]
                        ):
                            matches.append(
                                (box["top"], box["left"], index)
                            )
                    if matches:
                        return control[min(matches)[2]]
                    
            # 如果一直找不到唯一控件，直到超时就报错
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "控件不存在或匹配不唯一："
                    + json.dumps(rules, ensure_ascii=False)
                )
            
            time.sleep(0.2)

    def home_active():
        tree = ET.fromstring(
            d.dump_hierarchy(compressed=True)
        )
        parents = {
            child: parent
            for parent in tree.iter()
            for child in parent
        }

        for node in tree.iter("node"):
            if node.get("package") != package:
                continue

            labels = (
                node.get("text", "").strip(),
                node.get("content-desc", "").strip(),
            )
            if not any(
                re.fullmatch(
                    r"(?:首页|Home)(?:[,， ].*)?",
                    label,
                    flags=re.I,
                )
                for label in labels
            ):
                continue

            current = node
            for _ in range(4):
                if current is None:
                    break
                if current.get("selected") == "true":
                    return True
                current = parents.get(current)

        return False

    def open_search():
        find_control(selectors["search_button"]).click()
        wait_until(
            lambda: present(selectors["search_input"]),
            "搜索输入框未出现",
        )

    def input_keyword():
        field = find_control(selectors["search_input"])
        field.set_text(config["keyword"])

        wait_until(
            lambda: field.get_text() == config["keyword"],
            "搜索输入内容校验失败",
        )
        return {"value": config["keyword"]}
    
    def submit_search():
        d.press("enter")
        time.sleep(1.0)
        return {"verification": "deferred_until_video_open"}

    # def scroll_results():
    #     width, height = d.window_size()

    #     d.swipe(
    #         int(width * 0.50),
    #         int(height * 0.75),
    #         int(width * 0.50),
    #         int(height * 0.35),
    #         duration=0.3,
    #     )
    #     time.sleep(0.5)
    #     return {"direction": "up", "swipe_count": 1}

    def open_first_video():
        # width, height = d.window_size()

        # x_ratio = 0.5
        # y_ratio = 0.5

        # d.click(
        #     int(width * x_ratio),
        #     int(height * y_ratio),
        # )
        video = find_control(selectors["first_video"], first=True)
        video.click()

        def video_page_opened():
            search_query = d(
                packageName=package,
                resourceId=package + ":id/search_query",
            )

            return (
                not search_query.exists
                and present(selectors["player"])
                and not present(selectors["miniplayer"])
            )

        wait_until(
            video_page_opened,
            "点击视频标题后，视频详情页未打开",
        )

        result["video_opened_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )

        return {
            "method": "first_video_selector",
            "selector": selectors["first_video"],
            "player_page_verified": True,
        }

    def return_to_results():
        d.press("back")

        wait_until(
            lambda: d(
                packageName=package,
                resourceId=package + ":id/search_query",
            ).exists,
            "第一次返回后，搜索结果页未重新出现",
        )

        return {"search_query_visible": True}

    def return_to_home():
        d.press("back")
        wait_until(
            home_active,
            "第二次返回后，未检测到处于选中状态的首页标签",
        )
        result["home_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )

    def close_miniplayer():
        if not present(selectors["miniplayer"]):
            if not present(selectors["close_miniplayer"]):
                return {"method": "already_absent"}

        find_control(selectors["close_miniplayer"]).click()

        wait_until(
            lambda: (
                not present(selectors["miniplayer"])
                and not present(selectors["close_miniplayer"])
            ),
            "点击关闭后，小窗仍然可见",
        )
        wait_until(
            home_active,
            "关闭小窗后，首页标签校验失败",
        )

        return {
            "method": "resource_id",
            "miniplayer_closed": True,
        }

    try:
        connect_started = time.monotonic()
        d = u2.connect()

        result["connect_seconds"] = round(
            time.monotonic() - connect_started, 3
        )

        require_app_ui(d, package, timeout=args.timeout)

        result["home_preparation"] = ensure_youtube_home(d, package, args.timeout)
        wait_until(home_active, "未能恢复 YouTube 首页")

        if present(selectors["miniplayer"]):
            raise RuntimeError(
                "运行前请先关闭现有小窗"
            )

        result["initialization_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(
            "[%s] 初始化完成，耗时 %.3f 秒"
            % (app, result["initialization_seconds"]),
            flush=True,
        )

        steps = [
            ("open_search", open_search),
            ("input_keyword", input_keyword),
            ("submit_search", submit_search),
            # ("scroll_results", scroll_results),
            ("open_first_video", open_first_video),
            ("return_to_results", return_to_results),
            ("return_to_home", return_to_home),
            ("close_miniplayer", close_miniplayer),
        ]

        for index, (name, action) in enumerate(steps, 1):
            if index > 1 and args.interval:
                time.sleep(args.interval)

            if name == "return_to_results":
                remaining = max(
                    0.0,
                    SCRIPT_STARTED + args.time - time.monotonic(),
                )
                result["wait_before_return_seconds"] = round(
                    remaining, 3
                )

                if remaining:
                    print(
                        "[%s] 等待 %.3f 秒后返回"
                        % (app, remaining),
                        flush=True,
                    )
                    time.sleep(remaining)

                result["return_started_elapsed_seconds"] = round(
                    time.monotonic() - SCRIPT_STARTED, 3
                )

            row = {"name": name, "status": "RUNNING"}
            result["steps"].append(row)

            print(
                "[%s] 第 %02d 步：%s" % (app, index, step_labels.get(name, name)),
                flush=True,
            )

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
                "[%s] %s 已完成，耗时 %.3f 秒"
                % (app, step_labels.get(name, name), row["elapsed_seconds"]),
                flush=True,
            )
            step_started = None

        result["status"] = "PASS"

    except Exception as exc:
        error = "%s: %s" % (type(exc).__name__, exc)
        result["error"] = error
        save_failure(d, "youtube", result)

        if row is not None and row["status"] == "RUNNING":
            row.update(status="FAIL", error=error)
            if step_started is not None:
                row["elapsed_seconds"] = round(
                    time.monotonic() - step_started, 3
                )

        print("[%s] 失败：%s" % (app, error), flush=True)

    finally:
        result["elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
