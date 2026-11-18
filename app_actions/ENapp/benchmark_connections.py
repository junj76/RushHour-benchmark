"""Measure connections in fresh Python processes without opening or touching apps."""
import argparse
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time


BASE = Path(__file__).resolve().parent


def child(method, serial):
    started = time.monotonic()
    import uiautomator2 as u2
    from device_connection import connect_device
    imported = time.monotonic()
    device = u2.connect(serial) if method == "standard" else connect_device(serial)
    connected = time.monotonic()
    info = device.jsonrpc.deviceInfo(http_timeout=5)
    print(json.dumps({
        "method": method,
        "mode": getattr(device, "enapp_connection", {}).get("mode", "standard"),
        "imports_seconds": round(imported - started, 4),
        "connect_seconds": round(connected - imported, 4),
        "rpc_seconds": round(time.monotonic() - connected, 4),
        "connect_and_rpc_seconds": round(time.monotonic() - imported, 4),
        "rpc_verified": isinstance(info, dict),
    }), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--serial")
    parser.add_argument("--compare", action="store_true",
                        help="Stop the managed service, then measure standard and shared connections")
    parser.add_argument("--child", choices=["standard", "shared"], help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.samples < 1 or args.samples > 100:
        parser.error("samples must be 1..100")
    if args.child:
        child(args.child, args.serial)
        return 0
    folder = BASE / "timing_results" / ("connections_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    folder.mkdir(parents=True)
    serial_args = ["--serial", args.serial] if args.serial else []
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    if args.compare:
        stopped = subprocess.run([sys.executable, "-u", str(BASE / "device_connection.py"),
                                  "--stop"] + serial_args, env=env, capture_output=True, timeout=15)
        (folder / "stop.log").write_bytes(stopped.stdout + stopped.stderr)
        if stopped.returncode:
            print(stopped.stderr.decode("utf-8", errors="replace"))
            return stopped.returncode
        time.sleep(1)
    rows = []
    methods = ["standard", "shared"] if args.compare else ["shared"]
    for method in methods:
        for index in range(1, args.samples + 1):
            command = [sys.executable, "-u", str(Path(__file__).resolve()),
                       "--child", method] + serial_args
            started = time.monotonic()
            run = subprocess.run(command, env=env, capture_output=True, timeout=60)
            wall = round(time.monotonic() - started, 4)
            output = (run.stdout + run.stderr).decode("utf-8", errors="replace")
            (folder / ("%s_%02d.log" % (method, index))).write_text(output, encoding="utf-8")
            values = []
            for line in output.splitlines():
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if isinstance(value, dict) and "connect_seconds" in value:
                    values.append(value)
            if run.returncode or not values:
                print("Connection failed; inspect", folder, flush=True)
                return run.returncode or 1
            row = dict(values[-1], sample=index, process_wall_seconds=wall)
            rows.append(row)
            (folder / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
            print("%s %d: connect=%.4fs imports=%.4fs mode=%s RPC=%s" % (
                method, index, row["connect_seconds"], row["imports_seconds"],
                row["mode"], row["rpc_verified"]), flush=True)
            if method == "standard":

                time.sleep(1)
    with (folder / "summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for mode in dict.fromkeys(row["mode"] for row in rows):
        values = [row["connect_seconds"] for row in rows if row["mode"] == mode]
        print("%s median=%.4fs n=%d" % (mode, statistics.median(values), len(values)))
    print("Results:", folder, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
