import time
SCRIPT_STARTED = time.monotonic()
import argparse
import json
from pathlib import Path
from device_connection import connect_device
from app_ui import require_app_ui

def main():
    step_labels = {
        "browse_up": "返回天气页顶部",
        "browse_down": "向下浏览",
        "hourly_left": "向左浏览天气",
        "hourly_right": "向右浏览天气",
    }
    status_labels = {"PASS": "成功", "FAIL": "失败", "RUNNING": "执行中", "COMPLETED": "已完成"}

    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    cfg = json.loads((Path(__file__).parent / "profiles/weather.json")
                     .read_text(encoding="utf-8-sig"))
    result = {"app": "weather", "status": "FAIL", "steps": [],
              "verification": "gesture_execution_only"}

    def swipe_step(name):
        started = time.monotonic()
        item = {"name": name, "status": "FAIL"}
        print(f"[weather] {len(result['steps']) + 1:02d} {step_labels.get(name, name)}")

        try:
            horizontal = name in ("hourly_left", "hourly_right")
            control = d(
                packageName=cfg["package"],
                className=(
                    "android.view.View"
                    if horizontal else "android.widget.ScrollView"
                ),
                scrollable=True,
            )

            if not control.wait(timeout=min(args.timeout, 1.5)):
                raise RuntimeError(f"{step_labels.get(name, name)}: 滚动控件未出现")
            if control.count != 1:
                raise RuntimeError(f"{step_labels.get(name, name)}: 匹配到多个滚动控件")

            print("[weather] 已找到滚动控件，开始滑动", flush=True)
            info = control.info
            bounds = info.get("visibleBounds") or info["bounds"]
            left = max(0, bounds["left"])
            right = min(width, bounds["right"])
            top = max(0, bounds["top"])
            bottom = min(height, bounds["bottom"])

            if right <= left or bottom <= top:
                raise RuntimeError("滚动控件没有有效的可见区域")

            def point(x, y):
                return (
                    int(left + (right - left) * x),
                    int(top + (bottom - top) * y),
                )

            paths = {
                "hourly_left": ((0.8, 0.5), (0.2, 0.5)),
                "hourly_right": ((0.2, 0.5), (0.8, 0.5)),
                "browse_down": ((0.5, 0.8), (0.5, 0.2)),
                "browse_up": ((0.5, 0.2), (0.5, 0.8)),
            }
            start, end = paths[name]
            d.swipe(*point(*start), *point(*end), duration=0.25)

            time.sleep(max(args.interval, cfg["settle_seconds"]))
            item.update(
                status="PASS",
                detail={
                    "method": "control_bounds_system_swipe",
                    "position_verified": False,
                },
            )

        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            item["elapsed_seconds"] = round(
                time.monotonic() - started, 3
            )
            result["steps"].append(item)
            print(
                f"[weather] {step_labels.get(name, name)} {status_labels.get(item['status'], item['status'])} "
                f"，耗时 {item['elapsed_seconds']:.3f} 秒"
            )

    try:
        d = connect_device()
        d.implicitly_wait(0)
        require_app_ui(d, cfg['package'], timeout=args.timeout)
        width, height = d.window_size()
        result["initialization_seconds"] = round(time.monotonic() - SCRIPT_STARTED, 3)
        for name in ("hourly_left", "hourly_right", "browse_down"):
            swipe_step(name)
        remaining = max(0, SCRIPT_STARTED + args.time - time.monotonic())
        print(f"[weather] 等待 {remaining:.3f} 秒后恢复初始位置")
        time.sleep(remaining)
        swipe_step("browse_up")
        result["status"] = "COMPLETED"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["elapsed_seconds"] = round(time.monotonic() - SCRIPT_STARTED, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "COMPLETED" else 1

if __name__ == "__main__":
    raise SystemExit(main())
