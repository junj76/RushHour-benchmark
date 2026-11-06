"""Supervise scenario time and recover home in an independent, prearmed process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time


def extract_result(output, app):
    result = None
    decoder = json.JSONDecoder()
    for line in [0] + [i + 1 for i, char in enumerate(output) if char == "\n"]:
        if not output.startswith("{", line):
            continue
        try:
            value, _ = decoder.raw_decode(output, line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("app") == app and "steps" in value:
            result = value
    return result


def terminate(process):
    if process is not None and process.poll() is None:
        process.kill()
        process.wait(timeout=3)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def supervise(command, app, action_time, return_time, folder, max_time=None,
              recovery_command=None, prepare_limit=10):
    preparation = time.monotonic()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    child = worker = None
    chunks = []
    with tempfile.TemporaryDirectory(prefix="enapp-deadline-") as temp:
        temp = Path(temp)
        ready, recovered = temp / "ready.json", temp / "recovery.json"
        recover_cmd = recovery_command or [sys.executable, "-u", str(folder / "home_recovery.py"),
                                           "--app", app, "--config", str(folder / "profiles" / (app + ".json"))]
        try:
            with (temp / "recovery.log").open("w", encoding="utf-8") as recovery_log:
                worker = subprocess.Popen(recover_cmd + ["--ready", str(ready), "--result", str(recovered)],
                                          cwd=folder, env=env, stdin=subprocess.PIPE,
                                          stdout=recovery_log, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
                while not read_json(ready).get("ready"):
                    if worker.poll() is not None or time.monotonic() - preparation >= prepare_limit:
                        raise RuntimeError("Return controller preparation failed: " +
                                           read_json(recovered).get("error", "") + "\n" +
                                           (temp / "recovery.log").read_text(encoding="utf-8", errors="replace"))
                    time.sleep(0.02)
                preparation_seconds = time.monotonic() - preparation
                print("[deadline] controller ready in %.3fs; scenario clock starts now" % preparation_seconds, flush=True)
                started = time.monotonic()
                child = subprocess.Popen(command, cwd=folder, env=env, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")

                def relay():
                    for line in child.stdout:
                        chunks.append(line)
                        print(line, end="", flush=True)

                reader = threading.Thread(target=relay, daemon=True)
                reader.start()
                hit_deadline = False
                try:
                    child.wait(timeout=max(0, action_time - (time.monotonic() - started)))
                except subprocess.TimeoutExpired:
                    hit_deadline = True
                return_requested = time.monotonic() - started
                # Kill the action process before allowing any recovery command to run.
                terminate(child)
                print("[deadline] return requested at %.3fs; scenario stopped=%s" %
                      (return_requested, hit_deadline), flush=True)
                budget = return_time
                if max_time is not None:
                    budget = max(0, min(budget, max_time - (time.monotonic() - started)))
                return_started = time.monotonic() - started
                worker.stdin.write(json.dumps({"budget": budget}) + "\n")
                worker.stdin.flush()
                worker.stdin.close()
                try:
                    worker.wait(timeout=budget + 0.1)
                except subprocess.TimeoutExpired:
                    terminate(worker)
                recovery = read_json(recovered) or {
                    "home_verified": False, "error": "Return controller exceeded its time budget"}
                elapsed = time.monotonic() - started
                reader.join(timeout=0.2)
                original = extract_result("".join(chunks), app)
                result = dict(original or {"app": app, "steps": []})
                result["scenario_status"] = original.get("status") if original else (
                    "INTERRUPTED_AT_DEADLINE" if hit_deadline else "NO_RESULT")
                result["status"] = "HOME_FAILED"
                if recovery.get("home_verified"):
                    if (original and original.get("status") in {"FAIL", "TIMEOUT"}) or (original is None and not hit_deadline):
                        result["status"] = "FAIL"
                    else:
                        result["status"] = "DEADLINE_RETURNED" if hit_deadline else "COMPLETED"
                result.update(action_time_seconds=action_time,
                              controller_preparation_seconds=round(preparation_seconds, 3),
                              deadline_reached=hit_deadline, home_verified=recovery.get("home_verified", False),
                              return_requested_elapsed_seconds=round(return_requested, 3),
                              return_started_elapsed_seconds=round(return_started, 3),
                              elapsed_seconds=round(elapsed, 3), recovery=recovery)
                if recovery.get("home_verified"):
                    result["home_elapsed_seconds"] = round(elapsed, 3)
                else:
                    result.pop("home_elapsed_seconds", None)
                    result["error"] = recovery.get("error", "Home not verified")
                result["steps"] = list(result.get("steps", [])) + [{
                    "name": "return_deadline_home", "status": "PASS" if recovery.get("home_verified") else "FAIL",
                    "elapsed_seconds": round(elapsed - return_requested, 3), "detail": recovery}]
                return result, 0 if recovery.get("home_verified") and result["status"] != "FAIL" else 1
        finally:
            terminate(child)
            terminate(worker)
            if child is not None and child.stdout is not None:
                child.stdout.close()
            if worker is not None and worker.stdin is not None and not worker.stdin.closed:
                worker.stdin.close()
