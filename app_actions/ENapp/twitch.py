import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math
from pathlib import Path

import uiautomator2 as u2
from app_ui import require_app_ui
from flow_controls import capture, twitch_clean_home, twitch_close, twitch_overlay, save_failure


def main():
    step_labels = {
        "return_to_home": "返回首页",
        "close_miniplayer": "关闭小窗",
        "open_bottom_video": "打开底部可见视频",
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
        (Path(__file__).resolve().parent / "profiles" / "twitch.json")
        .read_text(encoding="utf-8-sig")
    )
    package = config["package"]
    result = {"app": "twitch", "package": package, "status": "FAIL", "steps": []}
    d = None

    def control(key, **extra):
        return d(packageName=package, **config["selectors"][key], **extra)

    def wait(check, message):
        deadline = time.monotonic() + args.timeout
        while not check():
            if time.monotonic() >= deadline:
                raise RuntimeError(message)
            time.sleep(0.15)

    def home():
        return (
            not control("chat").exists
            and control("feed").exists
            and control("home", selected=True).exists
        )

    def open_bottom_video():
        wait(home, "首页内容流尚未就绪")
        cards = control("card", clickable=True)
        choices = []
        for index in range(cards.count):
            info = cards[index].info
            box = info.get("visibleBounds") or info["bounds"]
            if box["bottom"] > box["top"] and box["right"] > box["left"]:
                choices.append((box["bottom"], index))
        if not choices:
            raise RuntimeError("未找到可见的视频卡片")
        _, index = max(choices)
        cards[index].click()
        result["video_clicked_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        return {
            "method": "bottom_visible_card_control",
            "player_page_verified": False,
            "playback_verified": False,
        }

    def return_to_feed():
        d.press("back")
        wait(home, "首页内容流未重新出现")
        return {"home_verified": True}

    def close_miniplayer():
        wait(home, "首页内容流尚未就绪")
        deadline = time.monotonic() + args.timeout
        clicked = False
        pattern = r"(?i)(?:close|dismiss|关闭|關閉).*"

        while time.monotonic() < deadline:
            overlay = d(
                packageName=package,
                descriptionMatches=r"(?i)(Show|Hide) mini player controls",
            )

            if overlay.count != 1:
                if twitch_clean_home(capture(d, package)):
                    time.sleep(0.3)
                    if twitch_clean_home(capture(d, package)):
                        return {
                            "method": "already_absent",
                            "miniplayer_closed": True,
                            "home_verified": True,
                        }
                time.sleep(0.1)
                continue

            box = overlay.info["bounds"]
            overlay.click(timeout=0.5)
            reveal_deadline = min(deadline, time.monotonic() + 1.5)

            while time.monotonic() < reveal_deadline:
                for button in (
                    d(packageName=package, descriptionMatches=pattern),
                    d(packageName=package, textMatches=pattern),
                ):
                    if button.count != 1:
                        continue
                    b = button.info["bounds"]
                    if (
                        box["left"] <= b["left"] < b["right"] <= box["right"]
                        and box["top"] <= b["top"] < b["bottom"] <= box["bottom"]
                    ):
                        button.click(timeout=0.5)
                        clicked = True
                        break
                if clicked:
                    break
                time.sleep(0.1)
            if clicked:
                break

        if not clicked:
            raise RuntimeError("已尝试显示小窗控制层，仍未找到关闭按钮")

        wait(
            lambda: twitch_clean_home(capture(d, package)),
            "点击关闭后，小窗仍未消失",
        )
        return {
            "method": "native_miniplayer_close_control",
            "miniplayer_closed": True,
            "home_verified": True,
        }

    def run_step(name, action, apply_interval=True):
        if apply_interval and result["steps"] and args.interval:
            time.sleep(args.interval)
        row = {"name": name, "status": "RUNNING"}
        result["steps"].append(row)
        print("[twitch] 第 %02d 步：%s" % (len(result["steps"]), step_labels.get(name, name)), flush=True)
        started = time.monotonic()
        try:
            row["detail"] = action()
            row["status"] = "PASS"
        except Exception as exc:
            row.update(status="FAIL", error="%s: %s" % (type(exc).__name__, exc))
            raise
        finally:
            row["elapsed_seconds"] = round(time.monotonic() - started, 3)
            print("[twitch] %s %s，耗时 %.3f 秒" % (
                step_labels.get(name, name), status_labels.get(row["status"], row["status"]), row["elapsed_seconds"]
            ), flush=True)

    try:
        started = time.monotonic()
        d = u2.connect()
        result["connect_seconds"] = round(time.monotonic() - started, 3)
        d.implicitly_wait(0)
        require_app_ui(d, package, timeout=args.timeout)
        if control("chat").exists or control("presenter").exists:
            result["initial_player_recovery"] = return_to_feed()
        home_tab = control("home")
        if home_tab.exists and not control("home", selected=True).exists:
            home_tab.click()
        wait(home, "请从 Twitch 首页内容流开始运行")
        if twitch_overlay(capture(d, package)):
            result["initial_miniplayer_recovery"] = close_miniplayer()
        if control("presenter").exists:
            raise RuntimeError("开始前请先关闭现有播放器")
        result["initialization_seconds"] = round(time.monotonic() - SCRIPT_STARTED, 3)
        print("[twitch] 初始化完成，耗时 %.3f 秒" % result["initialization_seconds"], flush=True)

        run_step("open_bottom_video", open_bottom_video)

        if args.interval:
            time.sleep(args.interval)

        remaining = max(
            0.0,
            SCRIPT_STARTED + args.time - time.monotonic(),
        )
        result["wait_before_return_seconds"] = round(remaining, 3)
        print(
            "[twitch] 继续观看 %.3f 秒后返回" % remaining,
            flush=True,
        )
        time.sleep(remaining)

        result["return_started_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        run_step(
            "return_to_home",
            return_to_feed,
            apply_interval=False,
        )
        result["home_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )

        run_step("close_miniplayer", close_miniplayer)

        result["home_clean_elapsed_seconds"] = round(
            time.monotonic() - SCRIPT_STARTED, 3
        )
        result["status"] = "PASS"
    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        save_failure(d, "twitch", result)
        print("[twitch] 失败：" + result["error"], flush=True)
    finally:
        result["elapsed_seconds"] = round(time.monotonic() - SCRIPT_STARTED, 3)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
