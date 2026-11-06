import time
SCRIPT_STARTED = time.monotonic()

import argparse
import json
from pathlib import Path

import uiautomator2 as u2
from app_ui import require_app_ui


def main():

    step_labels = {
        "open_and_input": "打开翻译输入框并输入文字",
        "submit_translation": "提交翻译",
        "wait_translation": "等待译文",
        "return_once1": "第一次返回",
        "return_once2": "第二次返回",
    }
    status_labels = {"PASS": "成功", "FAIL": "失败", "RUNNING": "执行中", "COMPLETED": "已完成"}

    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()

    cfg = json.loads(
        (Path(__file__).parent / "profiles" / "gtranslate.json")
        .read_text(encoding="utf-8-sig")
    )
    result = {"app": "gtranslate", "status": "FAIL", "steps": []}

    def step(name, action):
        started = time.monotonic()
        item = {"name": name, "status": "FAIL"}
        print(f"[gtranslate] {len(result['steps']) + 1:02d} {step_labels.get(name, name)}")
        try:
            item["detail"] = action() or {}
            item["status"] = "PASS"
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            item["elapsed_seconds"] = round(time.monotonic() - started, 3)
            result["steps"].append(item)
            print(f"[gtranslate] {step_labels.get(name, name)} {status_labels.get(item['status'], item['status'])} "
                  f"，耗时 {item['elapsed_seconds']:.3f} 秒")

    def input_text():
        field = d(resourceId=cfg["input_id"])

        if not field.exists:
            entry = d(
                packageName=cfg["package"],
                text="翻译文字",
            )
            if not entry.wait(timeout=args.timeout):
                entry = d(
                    packageName=cfg["package"],
                    description="翻译文字",
                )
                if not entry.wait(timeout=1):
                    raise RuntimeError("首页“翻译文字”入口未找到")

            if entry.count != 1:
                raise RuntimeError("首页“翻译文字”入口不唯一")

            entry.click()

        if not field.wait(timeout=args.timeout):
            raise RuntimeError("点击“翻译文字”后，输入框未出现")

        if field.count != 1:
            raise RuntimeError("翻译输入框不唯一")

        field.click()
        field.set_text(cfg["keyword"])

        if field.get_text() != cfg["keyword"]:
            raise RuntimeError("输入文字校验失败")

        return {
            "method": "home_text_control_then_input",
            "input_verified": True,
        }

    def submit():
        d.press("enter")
        return {"method": "enter_key", "physical_start_button_clicked": False}

    def wait_translation():
        translated = d(
            packageName=cfg["package"],
            textMatches=cfg["result_pattern"],
        )
        deadline = time.monotonic() + args.timeout
        while not translated.exists:
            if time.monotonic() >= deadline:
                raise RuntimeError("未检测到中文译文，需要提交后的页面 XML")
            time.sleep(max(args.interval, 0.1))
        return {"translation_text_verified": True}

    def return_once():
        d.press("back")
        time.sleep(0.5)
        return {"method": "android_back", "home_verified": False}

    try:
        d = u2.connect()
        d.implicitly_wait(0)
        require_app_ui(d, cfg['package'], timeout=args.timeout)

        result["initialization_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        step("open_and_input", input_text)
        step("submit_translation", submit)
        step("wait_translation", wait_translation)

        remaining = max(0, SCRIPT_STARTED + args.time - time.monotonic())
        print(f"[gtranslate] 等待 {remaining:.3f} 秒后返回")
        time.sleep(remaining)
        step("return_once1", return_once)
        step("return_once2", return_once)
        result["status"] = "COMPLETED"

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"

    result["elapsed_seconds"] = round(time.monotonic() - SCRIPT_STARTED, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
