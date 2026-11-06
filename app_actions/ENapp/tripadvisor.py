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
        "return_home": "返回首页",
        "open_recommended_card": "打开推荐卡片",
    }
    status_labels = {"PASS": "成功", "FAIL": "失败", "RUNNING": "执行中", "COMPLETED": "已完成"}

    p = argparse.ArgumentParser()
    p.add_argument("--time", type=float, default=10)
    p.add_argument("--interval", type=float, default=0.1)
    p.add_argument("--timeout", type=float, default=10)
    args = p.parse_args()
    cfg = json.loads((Path(__file__).parent / "profiles/tripadvisor.json")
                     .read_text(encoding="utf-8-sig"))
    result = {"app": "tripadvisor", "status": "FAIL", "steps": []}

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
            print(f"[tripadvisor] {step_labels.get(name, name)} {status_labels.get(item['status'], item['status'])} "
                  f"，耗时 {item['elapsed_seconds']:.3f} 秒")

    def open_card():
        card = d.xpath(f"(//*[@resource-id='{cfg['section_id']}']"
                       "//*[@clickable='true'])[1]")
        wait(lambda: bool(card.exists), "首页推荐卡片未出现")
        card.get().click()
        wait(lambda: not home(), "点击后仍停留在首页推荐区域")
        return {"method": "first_recommended_card_control"}

    def scroll_down():
        import xml.etree.ElementTree as ET

        content_id = "com.tripadvisor.tripadvisor:id/rvContent"
        target = d(resourceId=content_id)

        if not target.wait(timeout=args.timeout):
            raise RuntimeError("详情页正文滚动容器未出现")
        if target.count != 1:
            raise RuntimeError("正文滚动容器不唯一")

        def content_snapshot():
            root = ET.fromstring(d.dump_hierarchy())
            content = next(
                (
                    node for node in root.iter("node")
                    if node.get("resource-id") == content_id
                ),
                None,
            )
            if content is None:
                raise RuntimeError("正文滚动容器已消失")

            return tuple(
                (
                    node.get("text", ""),
                    node.get("content-desc", ""),
                    node.get("bounds", ""),
                )
                for node in content.iter("node")
                if node.get("text") or node.get("content-desc")
            )

        before = content_snapshot()
        if not before:
            raise RuntimeError("正文缺少可用于验证滚动的文字或描述")

        # 使用控件自身边界生成上滑手势。
        target.swipe("up", steps=cfg["scroll_steps"])
        time.sleep(max(args.interval, 0.5))

        deadline = time.monotonic() + 3.0
        while True:
            after = content_snapshot()
            if after and after != before:
                return {
                    "method": "content_control_swipe_up",
                    "content_layout_changed": True,
                }

            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "已在正文控件内上滑，但未检测到正文位置或内容变化"
                )
            time.sleep(max(args.interval, 0.2))

    def return_home():
        d.press("back")
        wait(home, "返回后未检测到首页")
        return {"method": "android_back", "home_verified": True}

    try:
        d = connect_device()
        d.implicitly_wait(0)
        home = lambda: (
            bool(d(resourceId=cfg["section_id"]).exists)
            and bool(d(resourceId=cfg["package"] + ":id/avatarSearchFieldRoot").exists)
        )
        require_app_ui(d, cfg['package'], timeout=args.timeout)
        step("open_recommended_card", open_card)
        step("browse_down_1", scroll_down)
        step("browse_down_2", scroll_down)
        remaining = max(0, SCRIPT_STARTED + args.time - time.monotonic())
        print(f"[tripadvisor] 等待 {remaining:.3f} 秒后返回")
        time.sleep(remaining)
        step("return_home", return_home)
        result["status"] = "PASS"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["elapsed_seconds"] = round(time.monotonic() - SCRIPT_STARTED, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
