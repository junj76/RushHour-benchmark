import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

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
    parser.add_argument(
        "--max-time",
        type=float,
        default=None,
        help="整个应用脚本的最长运行秒数，包含初始化和返回",
    )
    args = parser.parse_args()

    if args.max_time is not None and args.max_time <= 0:
        parser.error("--max-time 必须大于 0")

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
        completed = subprocess.run(command, timeout=args.max_time)
        return completed.returncode
    except subprocess.TimeoutExpired:
        result = {
            "app": args.app,
            "status": "TIMEOUT",
            "error": "达到总运行时间上限，已终止应用脚本",
            "max_time_seconds": args.max_time,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
