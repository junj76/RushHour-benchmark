import time
SCRIPT_STARTED = time.monotonic()

import argparse
import json
from pathlib import Path
import uiautomator2 as u2
from flow_controls import save_failure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()

    cfg = json.loads(
        (Path(__file__).parent / "profiles/wiki.json")
        .read_text(encoding="utf-8-sig")
    )
    package = cfg["package"]
    deadline = SCRIPT_STARTED + args.time
    result = {"app": "wiki", "status": "FAIL", "steps": []}
    d = None

    def wait(check, message, timeout=None):
        stop = time.monotonic() + (args.timeout if timeout is None else timeout)
        while True:
            value = check()
            if value:
                return value
            if time.monotonic() >= stop:
                raise RuntimeError(message)
            time.sleep(max(args.interval, 0.15))

    def step(name, action):
        started = time.monotonic()
        row = {"name": name, "status": "FAIL"}
        print(f"[wiki] {name}", flush=True)
        try:
            row["detail"] = action() or {}
            row["status"] = "PASS"
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            row["elapsed_seconds"] = round(
                time.monotonic() - started, 3
            )
            result["steps"].append(row)
            print(
                f"[wiki] {name} {row['status']}，"
                f"耗时 {row['elapsed_seconds']:.3f}s",
                flush=True,
            )

    try:
        d = u2.connect()
        d.implicitly_wait(0)

        field = d(
            packageName=package,
            resourceId=package + ":id/search_src_text",
        )
        articles = d.xpath(
            f"//*[@package='{package}'"
            " and @resource-id='searchresults_list']"
            "/*[@clickable='true' and @enabled='true']"
        )

        def open_search():
            button = d(
                packageName=package,
                resourceId=package + ":id/search_button",
            )
            if not button.wait(timeout=args.timeout):
                raise RuntimeError("未找到首页右上角搜索按钮")
            button.click()
            wait(lambda: bool(field.exists), "搜索输入框未出现")
            return {"method": "search_button_control"}

        def input_keyword():
            field.click()
            field.set_text(cfg["keyword"])
            wait(
                lambda: field.get_text() == cfg["keyword"],
                "搜索文字校验失败",
            )
            return {"keyword": cfg["keyword"], "input_verified": True}

        def submit_search():
            d.press("enter")
            wait(
                lambda: bool(articles.exists),
                "Enter 未触发搜索或文章列表尚未加载",
            )
            return {
                "method": "enter_key",
                "article_results_verified": True,
            }

        def article_page_ready():
            pages = d(
                packageName=package,
                className="android.webkit.WebView",
                scrollable=True,
            )
            if pages.count != 1 or articles.exists:
                return False
            # 当前版本 WebView 自身 text 为空，文章标题位于 section_0 子控件。
            heading = d(packageName=package, resourceId="section_0")
            return heading.exists and bool(heading.get_text().strip())

        def open_article():
            matches = wait(
                lambda: articles.all(),
                "未找到文章结果",
            )
            first = matches[0]
            description = first.attrib.get("content-desc", "")
            first.click()
            wait(article_page_ready, "点击后未检测到文章页面")
            return {
                "method": "first_article_control",
                "description": description,
                "article_page_verified": True,
            }

        def read_until_time():
            count = 0
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining < 1.5:
                    time.sleep(max(0, remaining))
                    break

                page = d(
                    packageName=package,
                    className="android.webkit.WebView",
                    scrollable=True,
                )
                if page.count != 1:
                    raise RuntimeError("文章滚动容器不存在或不唯一")

                page.swipe("up", steps=cfg["swipe_steps"])
                count += 1
                time.sleep(min(
                    cfg["read_pause"],
                    max(0, deadline - time.monotonic()),
                ))

            return {
                "method": "article_webview_swipe",
                "swipe_count": count,
                "movement_verified": False,
            }

        def return_results():
            d.press("back")
            wait(
                lambda: bool(articles.exists),
                "第一次返回后，文章列表未出现",
            )
            return {"results_verified": True}

        def return_home():
            time.sleep(0.4)
            d.press("back")
            return {"method": "android_back", "home_verified": False}

        step("open_search", open_search)
        step("input_keyword", input_keyword)
        step("submit_search", submit_search)
        step("open_first_article", open_article)
        step("read_until_time", read_until_time)

        result["return_started_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        step("return_to_results", return_results)
        step("return_to_home", return_home)
        result["status"] = "PASS"

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[wiki] FAIL: {result['error']}", flush=True)
        save_failure(d, "wiki", result)
        if d is not None:
            try:
                folder = Path(__file__).resolve().parent / "ui_dumps"
                folder.mkdir(exist_ok=True)
                image = folder / f"wiki_failure_{time.time_ns()}.png"
                d.screenshot(str(image))
                result["failure_screenshot"] = str(image)
            except Exception as capture_error:
                result["failure_screenshot_error"] = str(capture_error)

    result["elapsed_seconds"] = round(
        time.monotonic() - SCRIPT_STARTED, 3
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
