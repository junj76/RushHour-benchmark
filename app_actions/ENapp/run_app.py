import argparse
import json
from pathlib import Path
import sys
import time
import math

from deadline_runner import supervise

BASE_DIR = Path(__file__).resolve().parent

# app 列表
APP_SCRIPTS = {
    "gmap": "gmap.py",
    "youtube": "youtube.py",
    "gmail": "gmail.py",
    "ins": "ins.py",
    "twitch": "twitch.py",
    "reddit": "reddit.py",
    "chatgpt": "chatgpt.py",
    "google": "google.py",
    "tiktok": "tiktok.py",
    "github": "github.py",
    "spotify": "spotify.py",
    "uber": "uber.py",
    "booking": "booking.py",
    "pinterest": "pinterest.py",
    "foodpanda": "foodpanda.py",
    "wiki":"wiki.py",
    "weather":"weather.py",
    "gtranslate":"gtranslate.py",
    "tripadvisor":"tripadvisor.py",
    "aliexpress":"aliexpress.py",
    "youtube_shorts": "youtube_shorts.py"
}


def main():
    started = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True, choices=sorted(APP_SCRIPTS))
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--return-timeout", type=float, default=8,
                        help="到时返回首页的单独预算（秒），正常返回失败时允许重启应用")
    parser.add_argument(
        "--max-time",
        type=float,
        default=None,
        help="整个应用脚本的最长运行秒数，包含初始化和返回",
    )
    args = parser.parse_args()

    if not all(math.isfinite(value) for value in (args.time, args.interval, args.timeout, args.return_timeout)):
        parser.error("时间参数必须是有限数字")
    if args.time < 0 or args.interval < 0 or args.timeout <= 0 or args.return_timeout <= 0:
        parser.error("time/interval >= 0; timeout/return-timeout > 0")
    if args.max_time is not None and (not math.isfinite(args.max_time) or args.max_time <= args.time):
        parser.error("--max-time 必须大于 --time，为返回首页预留时间")

    script_path = BASE_DIR / APP_SCRIPTS[args.app]
    if not script_path.is_file():
        parser.error("未找到应用脚本：%s" % script_path)

    command = [
        sys.executable, "-u", str(script_path),
        "--time", str(args.time),
        "--interval", str(args.interval),
        "--timeout", str(args.timeout),
    ]

    try:
        result, code = supervise(command, args.app, args.time, args.return_timeout,
                                 BASE_DIR, max_time=args.max_time)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        result, code = {"app": args.app, "status": "SETUP_ERROR", "steps": [],
                        "home_verified": False, "error": str(exc),
                        "elapsed_seconds": round(time.monotonic() - started, 3)}, 1
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
