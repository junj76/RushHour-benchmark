import time

SCRIPT_STARTED = time.monotonic()

import argparse
import json
import math

import uiautomator2 as u2

from run_app import EXIT_CODES, ROOT, run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type=float, default=0)
    parser.add_argument("--interval", type=float, default=0)
    parser.add_argument(
        "--app",
        required=True,
        choices=sorted(
            path.stem
            for path in (ROOT / "profiles").glob("*.json")
        ),
    )
    args = parser.parse_args()

    if not math.isfinite(args.time) or args.time < 0:
        parser.error("--time must be finite and nonnegative")
    if not math.isfinite(args.interval) or args.interval < 0:
        parser.error("--interval must be finite and nonnegative")

    connect_started = time.monotonic()
    device = u2.connect()

    startup_timing = {
        "cli_and_import": round(
            connect_started - SCRIPT_STARTED, 3
        ),
        "connect": round(
            time.monotonic() - connect_started, 3
        ),
    }

    result = run(
        device,
        args.app,
        hold_seconds=args.time,
        script_started=SCRIPT_STARTED,
        interval_seconds=args.interval,
        startup_timing=startup_timing,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_CODES[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())