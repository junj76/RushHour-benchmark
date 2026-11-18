"""Run existing ENapp scenarios sequentially and collect their reported timings."""
import argparse
import ast
import csv
from datetime import datetime
import html
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


FIELDS = [
    "app", "status", "launch_seconds", "script_wall_seconds",
    "reported_elapsed_seconds", "initialization_seconds",
    "return_started_elapsed_seconds", "reported_home_elapsed_seconds",
    "return_steps_seconds", "return_steps_status", "reported_home_verified",
    "slowest_step", "slowest_step_seconds", "exit_code", "error", "log",
]


def registry(folder):
    tree = ast.parse((folder / "run_app.py").read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "APP_SCRIPTS"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("APP_SCRIPTS not found in run_app.py")


def extract_result(output, app):
    decoder = json.JSONDecoder()
    result = None
    for line_start in [0] + [i + 1 for i, char in enumerate(output) if char == "\n"]:
        if not output.startswith("{", line_start):
            continue
        try:
            value, _ = decoder.raw_decode(output, line_start)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("app") == app and "steps" in value:
            result = value
    return result


def stop_process(process):
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if process.poll() is None:
            process.kill()
    process.wait()


def run_logged(command, log, limit, cwd, env):
    started = time.monotonic()
    timed_out = False
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT,
            start_new_session=(os.name == "posix"),
        )
        try:
            process.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop_process(process)
        except BaseException:
            stop_process(process)
            raise
    return process.returncode, round(time.monotonic() - started, 3), timed_out


def is_return(name):
    return name.startswith(("return_", "back_", "browse_up")) or name in {
        "tap_home", "verify_home", "close_miniplayer", "restore", "back",
    }


def summarize(app, result, wall, code, timed_out, log):
    row = {key: None for key in FIELDS}
    row.update(app=app, script_wall_seconds=wall, exit_code=code, log=str(log))
    steps = result.get("steps", []) if result else []
    row["status"] = "TIMEOUT" if timed_out else (
        result.get("status", "NO_RESULT") if result else "NO_RESULT"
    )
    if code and row["status"] in {"PASS", "COMPLETED"}:
        row["status"] = "PROCESS_ERROR"
    if result:
        for key in ("initialization_seconds", "return_started_elapsed_seconds"):
            row[key] = result.get(key)
        row["reported_elapsed_seconds"] = result.get("elapsed_seconds")
        row["reported_home_elapsed_seconds"] = result.get("home_elapsed_seconds")
        row["reported_home_verified"] = result.get("home_verified")
        if row["reported_home_verified"] is None:
            flags = [step.get("detail", {}).get("home_verified") for step in steps]
            flags = [flag for flag in flags if isinstance(flag, bool)]
            row["reported_home_verified"] = flags[-1] if flags else None
        row["error"] = result.get("error")
    if timed_out:
        row["error"] = "Batch time limit reached; partial log retained"
    elif not result:
        row["error"] = "No complete result JSON; inspect log"
    returns = [step for step in steps if is_return(step.get("name", ""))]
    if returns:
        row["return_steps_seconds"] = round(sum(
            step.get("elapsed_seconds", 0) or 0 for step in returns), 3)
        row["return_steps_status"] = (
            "PASS" if all(step.get("status") == "PASS" for step in returns) else "FAIL"
        )
    else:
        row["return_steps_status"] = "NO_RECORDED_STEPS"
    measured = [step for step in steps if isinstance(step.get("elapsed_seconds"), (int, float))]
    if measured:
        slowest = max(measured, key=lambda step: step["elapsed_seconds"])
        row["slowest_step"] = slowest["name"]
        row["slowest_step_seconds"] = slowest["elapsed_seconds"]
    return row


def write_reports(folder, rows, results):
    ordered = sorted(rows, key=lambda row: row.get("script_wall_seconds") or 0, reverse=True)
    with (folder / "summary.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(ordered)
    with (folder / "steps.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["app", "step", "status", "elapsed_seconds", "error", "detail"])
        for result in results:
            for step in result.get("steps", []):
                writer.writerow([result["app"], step.get("name"), step.get("status"),
                                 step.get("elapsed_seconds"), step.get("error"),
                                 json.dumps(step.get("detail", {}), ensure_ascii=False)])
    (folder / "results.json").write_text(
        json.dumps({"summary": ordered, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    columns = [
        ("app", "App"), ("status", "Status"), ("launch_seconds", "Launch (s)"),
        ("script_wall_seconds", "Script total (s)"),
        ("initialization_seconds", "Initialization (s)"),
        ("return_started_elapsed_seconds", "Return starts at (s)"),
        ("return_steps_seconds", "Return/restore steps (s)"),
        ("return_steps_status", "Return steps status"),
        ("reported_home_verified", "Home verified by script"),
        ("slowest_step", "Slowest step"), ("slowest_step_seconds", "Slowest step (s)"),
    ]
    cells = []
    maximum = max([row.get("script_wall_seconds") or 0 for row in rows] + [1])
    for row in ordered:
        parts = []
        for key, _ in columns:
            value = row.get(key)
            label = "--" if value is None else str(value)
            if key == "app":
                parts.append('<td><a href="logs/%s.log">%s</a></td>' %
                             (html.escape(row["app"], quote=True), html.escape(label)))
            elif key == "script_wall_seconds":
                parts.append('<td>%s <meter min="0" max="%s" value="%s"></meter></td>' %
                             (html.escape(label), maximum, value or 0))
            else:
                parts.append("<td>%s</td>" % html.escape(label))
        cells.append("<tr>" + "".join(parts) + "</tr>")
    document = '''<!doctype html><meta charset="utf-8"><title>App timings</title>
<style>body{font:14px system-ui;margin:24px;color:#202124}table{border-collapse:collapse}
th,td{border-bottom:1px solid #ddd;padding:9px;text-align:left;white-space:nowrap}
th{background:#edf3f0}meter{width:110px}a{color:#075bba}</style>
<h1>App timings</h1><p>Sorted by script wall time, descending. -- means unavailable.
Return steps are reported by the scripts; they do not independently prove arrival home.
TIMEOUT is a capped measurement, not a completed run. Launch time is separate.</p><table>
<thead><tr>''' + "".join("<th>%s</th>" % title for _, title in columns) + \
        "</tr></thead><tbody>" + "".join(cells) + "</tbody></table>"
    (folder / "report.html").write_text(document, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--apps", nargs="+")
    parser.add_argument("--include-shorts", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--manual", action="store_true", help="Confirm each app's required start page")
    parser.add_argument("--serial")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--time", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--limit", type=float, default=60, help="Per-script diagnostic cap in seconds")
    parser.add_argument("--launch-limit", type=float, default=20)
    parser.add_argument("--settle", type=float, default=2)
    args = parser.parse_args()
    folder = args.dir.resolve()
    if not all(math.isfinite(getattr(args, key)) for key in
               ("time", "interval", "timeout", "limit", "launch_limit", "settle")):
        parser.error("Time values must be finite")
    if min(args.time, args.interval, args.settle) < 0 or min(args.timeout, args.limit, args.launch_limit) <= 0:
        parser.error("time/interval/settle >= 0; timeout/limit/launch-limit > 0")
    mapping = registry(folder)
    apps = args.apps or [app for app in mapping if args.include_shorts or app != "youtube_shorts"]
    if len(set(apps)) != len(apps) or any(app not in mapping for app in apps):
        parser.error("Unknown or duplicate app in --apps")
    if args.list:
        print("\n".join(apps))
        print("Total:", len(apps))
        return 0
    adb = shutil.which(args.adb)
    if not adb:
        parser.error("adb not found")
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", ADBUTILS_ADB_PATH=adb)
    listing = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=15, check=True)
    devices = [line.split()[0] for line in listing.stdout.splitlines()
               if len(line.split()) == 2 and line.split()[1] == "device"]
    serial = args.serial or os.environ.get("ANDROID_SERIAL")
    if serial is None and len(devices) == 1:
        serial = devices[0]
    if serial not in devices:
        parser.error("Select one authorized device with --serial; connected: " + repr(devices))
    env["ANDROID_SERIAL"] = serial
    adb_command = [adb, "-s", serial]
    packages_result = subprocess.run(adb_command + ["shell", "pm", "list", "packages"],
                                     capture_output=True, text=True, timeout=20, check=True)
    installed = {line.strip().removeprefix("package:") for line in packages_result.stdout.splitlines()}
    output = folder / "timing_results" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    (output / "logs").mkdir(parents=True)
    rows, results = [], []
    (output / "settings.json").write_text(json.dumps(
        {**vars(args), "dir": str(folder), "serial": serial, "apps": apps}, indent=2), encoding="utf-8")
    print("Output:", output, flush=True)
    for index, app in enumerate(apps, 1):
        print("[%d/%d] %s" % (index, len(apps), app), flush=True)
        log = output / "logs" / (app + ".log")
        launch_started = time.monotonic()
        launch_seconds = None
        try:
            config = json.loads((folder / "profiles" / (app + ".json")).read_text(encoding="utf-8-sig"))
            packages = config.get("packages") or [config["package"]]
            package = next((item for item in packages if item in installed), None)
            if not package:
                raise RuntimeError("App not installed: " + repr(packages))
            resolved = subprocess.run(adb_command + [
                "shell", "cmd", "package", "resolve-activity", "--brief", "-a",
                "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", package,
            ], capture_output=True, text=True, timeout=args.launch_limit, check=True)
            components = [line.strip() for line in resolved.stdout.splitlines()
                          if line.strip().startswith(package + "/")]
            if not components:
                raise RuntimeError("Launcher activity not resolved: " + resolved.stdout.strip())
            launch_log = output / "logs" / (app + ".launch.log")
            code, _, expired = run_logged(adb_command + ["shell", "am", "start", "-W", "-n", components[-1]],
                                          launch_log, args.launch_limit, folder, env)
            launch_seconds = round(time.monotonic() - launch_started, 3)
            launch_text = launch_log.read_text(encoding="utf-8", errors="replace")
            if expired or code or "Error:" in launch_text or "Exception" in launch_text or "Status: timeout" in launch_text:
                raise RuntimeError("Launch failed/timed out; inspect " + str(launch_log))
            if args.manual:
                answer = input("Prepare %s start page. Enter=run, s=skip: " % app).strip().lower()
                if answer == "s":
                    rows.append({"app": app, "status": "SKIPPED", "launch_seconds": launch_seconds})
                    write_reports(output, rows, results)
                    continue
            else:
                time.sleep(args.settle)
            # Execute the actual app script so run_app.py's cap cannot truncate diagnostics.
            command = [sys.executable, "-u", str(folder / mapping[app]),
                       "--time", str(args.time), "--interval", str(args.interval),
                       "--timeout", str(args.timeout)]
            code, wall, expired = run_logged(command, log, args.limit, folder, env)
            result = extract_result(log.read_text(encoding="utf-8", errors="replace"), app)
            row = summarize(app, result, wall, code, expired, log)
            row["launch_seconds"] = launch_seconds
            if result:
                results.append(result)
        except KeyboardInterrupt:
            write_reports(output, rows, results)
            print("Stopped. Completed results retained:", output, flush=True)
            return 130
        except Exception as exc:
            row = {"app": app, "status": "SETUP_ERROR", "launch_seconds": launch_seconds,
                   "error": str(exc), "log": str(log)}
            with log.open("a", encoding="utf-8") as stream:
                stream.write(str(exc) + "\n")
        rows.append(row)
        write_reports(output, rows, results)
        print("  %s total=%s return_steps=%s slowest=%s" % (
            row["status"], row.get("script_wall_seconds"), row.get("return_steps_seconds"),
            row.get("slowest_step")), flush=True)
    print("\nAPP                  STATUS          TOTAL(s)  RETURN(s)  SLOWEST STEP")
    for row in sorted(rows, key=lambda item: item.get("script_wall_seconds") or 0, reverse=True):
        print("%-20s %-15s %-9s %-10s %s" % (row["app"], row["status"],
              row.get("script_wall_seconds", "--"), row.get("return_steps_seconds", "--"),
              row.get("slowest_step", "--")))
    print("Report:", output / "report.html", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
