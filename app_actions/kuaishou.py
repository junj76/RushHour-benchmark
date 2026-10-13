import time
STARTED = time.monotonic()
import argparse
import json
from pathlib import Path
import uiautomator2 as u2

parser = argparse.ArgumentParser()
parser.add_argument("--serial", required=True)
args = parser.parse_args()
path = Path(__file__).resolve()
config = json.loads(
    (path.parent / "profiles" / (path.stem + ".json")).read_text(encoding="utf-8")
)
interval = float(config["interval_seconds"])
duration = float(config["swipe_duration"])
budget = float(config["max_seconds"])
count = config["swipe_count"]
if min(interval, duration, budget) <= 0:
    raise ValueError("Timing values must be positive")
if type(count) is not int or count < 1:
    raise ValueError("swipe_count must be a positive integer")

def check_time():
    if time.monotonic() - STARTED >= budget:
        raise TimeoutError("Execution exceeded %.1fs" % budget)

result = {"app": config["app"], "status": "FAIL", "completed_swipes": 0}
try:
    check_time()
    d = u2.connect(args.serial)
    check_time()
    info = d.info
    if info.get("screenOn") is False:
        raise RuntimeError("Device screen is off")
    package = info.get("currentPackageName") or d.app_current().get("package")
    if package != config["package"]:
        raise RuntimeError("Open the configured app in the foreground")
    width, height = d.window_size()
    for _ in range(count):
        check_time()
        if time.monotonic() + interval >= STARTED + budget:
            raise TimeoutError("Insufficient time for the next swipe")
        time.sleep(interval)
        check_time()
        d.swipe(int(width*.5), int(height*.75),
                int(width*.5), int(height*.35), duration=duration)
        result["completed_swipes"] += 1
        check_time()
    result["status"] = "PASS"
except Exception as exc:
    result["status"] = "TIMEOUT" if isinstance(exc, TimeoutError) else "FAIL"
    result["error"] = str(exc)
result["elapsed_seconds"] = round(time.monotonic() - STARTED, 3)
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["status"] == "PASS" else 1)