import time

SCRIPT_STARTED = time.monotonic()

import argparse
import importlib.util
from pathlib import Path
import sys


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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--app",
        required=True,
        choices=sorted(APP_SCRIPTS),
    )
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()

    script_path = BASE_DIR / APP_SCRIPTS[args.app]
    if not script_path.is_file():
        parser.error("未找到应用脚本：%s" % script_path)

    spec = importlib.util.spec_from_file_location(
        "_enapp_" + args.app,
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    module.SCRIPT_STARTED = SCRIPT_STARTED

    original_argv = sys.argv
    sys.argv = [
        str(script_path),
        "--time", str(args.time),
        "--interval", str(args.interval),
        "--timeout", str(args.timeout),
    ]

    try:
        return module.main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
