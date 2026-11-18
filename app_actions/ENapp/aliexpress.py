import time
SCRIPT_STARTED = time.monotonic()
import argparse
import json
from pathlib import Path
from device_connection import connect_device
from app_ui import require_app_ui


def main():
    step_labels = {
        "browse_down_1": "第一次向下浏览",
        "browse_down_2": "第二次向下浏览",
        "open_product": "打开商品",
        "return_home": "返回首页",
    }
    status_labels = {"PASS": "成功", "FAIL": "失败", "RUNNING": "执行中", "COMPLETED": "已完成"}

    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    cfg = json.loads((Path(__file__).parent / "profiles/aliexpress.json")
                     .read_text(encoding="utf-8-sig"))
    result = {"app": "aliexpress", "status": "FAIL", "steps": [],
              "verification": "action_execution_only"}

    def wait(check, message):
        deadline = time.monotonic() + args.timeout
        while True:
            value = check()
            if value:
                return value
            if time.monotonic() >= deadline:
                raise RuntimeError(message)
            time.sleep(max(args.interval, 0.1))

    def step(name, action):
        started = time.monotonic()
        item = {"name": name, "status": "FAIL"}
        try:
            item["detail"] = action() or {}
            item["status"] = "PASS"
        except Exception as exc:
            item["error"] = str(exc)
            raise
        finally:
            item["elapsed_seconds"] = round(time.monotonic() - started, 3)
            result["steps"].append(item)
            print(f"[aliexpress] {step_labels.get(name, name)} {status_labels.get(item['status'], item['status'])} "
                  f"，耗时 {item['elapsed_seconds']:.3f} 秒")

    def home():
        return (
            bool(d(resourceId=cfg["package"] + ":id/iv_top_logo").exists)
            and bool(d(resourceId=cfg["package"] + ":id/home_tab_layout").exists)
        )

    def open_product():
        cards = d.xpath(
            f"//*[@resource-id='{cfg['package']}:id/root_recycler_view']"
            "//*[@clickable='true' and contains(@content-desc,' . US $')"
            " and contains(@content-desc,'. link')]"
        )
        matches = wait(lambda: cards.all(), "首页商品卡片未出现")
        matches[0].click()
        wait(lambda: not home(), "点击商品后仍停留在首页")
        return {"method": "first_product_card_control",
                "product_detail_verified": False}

    def browse_down():
        classes = (
            "self::android.widget.ScrollView or "
            "self::android.widget.ListView or "
            "self::androidx.core.widget.NestedScrollView or "
            "self::androidx.recyclerview.widget.RecyclerView or "
            "self::android.webkit.WebView"
        )
        containers = d.xpath(
            f"//*[@package='{cfg['package']}' and @scrollable='true']"
            f"[{classes}]"
            f"[not(ancestor::*[@scrollable='true'][{classes}])]"
        )
        matches = wait(lambda: containers.all(), "未找到详情页滚动容器")
        if len(matches) != 1:
            raise RuntimeError("详情页存在多个滚动容器，需要详情页 XML")
        matches[0].swipe("up")
        time.sleep(max(args.interval, cfg["settle_seconds"]))
        return {"method": "content_control_swipe_up",
                "movement_verified": False}

    def return_home():
        d.press("back")
        wait(home, "返回后未检测到首页")
        return {"method": "android_back", "home_verified": True}

    try:
        d = connect_device()
        d.implicitly_wait(0)
        require_app_ui(d, cfg['package'], timeout=args.timeout)
        wait(home, "请从 AliExpress 首页开始")
        step("open_product", open_product)
        step("browse_down_1", browse_down)
        step("browse_down_2", browse_down)
        remaining = max(0, SCRIPT_STARTED + args.time - time.monotonic())
        print(f"[aliexpress] 等待 {remaining:.3f} 秒后返回")
        time.sleep(remaining)
        step("return_home", return_home)
        result["status"] = "COMPLETED"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["elapsed_seconds"] = round(time.monotonic() - SCRIPT_STARTED, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
