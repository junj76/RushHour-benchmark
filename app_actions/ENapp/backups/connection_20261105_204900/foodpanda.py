import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
from pathlib import Path

import uiautomator2 as u2
from app_ui import require_app_ui


def main():
    step_labels = {
        "open_manual_address": "打开手动填写地址页面",
        "wait_and_confirm": "等待并确认",
        "return_1": "第一次返回",
        "return_2": "第二次返回",
        "verify_home": "确认首页已出现",
    }
    status_labels = {"PASS": "成功", "FAIL": "失败", "RUNNING": "执行中", "COMPLETED": "已完成"}

    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()

    config = json.loads(
        (Path(__file__).parent / "profiles" / "foodpanda.json")
        .read_text(encoding="utf-8-sig")
    )
    result = {
        "app": "foodpanda",
        "package": config["package"],
        "status": "FAIL",
        "steps": [],
    }
    poll = max(args.interval, 0.1)

    def wait_control(label):
        deadline = time.monotonic() + args.timeout
        while True:
            for selector in (
                device(text=label, enabled=True),
                device(description=label, enabled=True),
            ):
                if selector.exists and selector.count == 1:
                    return selector
            if time.monotonic() >= deadline:
                raise RuntimeError(f"未找到可用控件：{label}")
            time.sleep(poll)

    def step(name, action):
        print(f"[foodpanda] {len(result['steps']) + 1:02d} {step_labels.get(name, name)}")
        started = time.monotonic()
        item = {"name": name}
        try:
            item["detail"] = action() or {}
            item["status"] = "PASS"
        except Exception as exc:
            item.update(
                status="FAIL",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        finally:
            item["elapsed_seconds"] = round(
                time.monotonic() - started, 3
            )
            result["steps"].append(item)
            print(
                f"[foodpanda] {step_labels.get(name, name)} {status_labels.get(item['status'], item['status'])} "
                f"，耗时 {item['elapsed_seconds']:.3f} 秒"
            )

    def click_label(label):
        wait_control(label).click()
        return {"method": "label_control", "label": label}

    def return_once():
        # 缓存屏幕尺寸，避免每次滑动重复查询。
        if not hasattr(return_once, "screen_size"):
            return_once.screen_size = device.window_size()

        width, height = return_once.screen_size

        device.swipe(
            1,
            height // 2,
            int(width * 0.65),
            height // 2,
            duration=0.2,
        )
        time.sleep(1.2)

        return {
            "method": "left_edge_swipe_right",
            "navigation_verified": False,
        }

    try:
        started = time.monotonic()
        device = u2.connect()
        device.implicitly_wait(0)
        result["connect_seconds"] = round(
            time.monotonic() - started, 3
        )

        require_app_ui(device, config['package'], timeout=args.timeout)

        wait_control(config["manual_label"])
        result["initialization_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        print(
            "[foodpanda] 初始化完成，耗时 "
            f"{result['initialization_seconds']:.3f} 秒"
        )

        step(
            "open_manual_address",
            lambda: click_label(config["manual_label"]),
        )
        step(
            "wait_and_confirm",
            lambda: click_label(config["confirm_label"]),
        )

        remaining = max(
            0.0, SCRIPT_STARTED + args.time - time.monotonic()
        )
        result["wait_before_return_seconds"] = round(remaining, 3)
        print(f"[foodpanda] 等待 {remaining:.3f} 秒后返回")
        time.sleep(remaining)

        result["return_started_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        step("return_1", return_once)
        step("return_2", return_once)

        def verify_home():
            wait_control(config["manual_label"])
            return {"manual_address_control_visible": True}

        step("verify_home", verify_home)
        result["status"] = "PASS"

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[foodpanda] 失败：{result['error']}")

    result["elapsed_seconds"] = round(
        time.monotonic() - SCRIPT_STARTED, 3
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
