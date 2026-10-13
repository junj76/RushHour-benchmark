import argparse
import json
import time
from pathlib import Path

import uiautomator2 as u2


BASE_DIR = Path(__file__).resolve().parent
CONFIG = json.loads(
    (BASE_DIR / "profiles" / "baidu.json").read_text(encoding="utf-8")
)

def result_body_visible(device):
    image = device.screenshot().convert("RGB")
    w, h = image.size
    region = image.crop((
        int(w * 0.20), int(h * 0.175),
        int(w * 0.70), int(h * 0.230),
    )).resize((100, 40))
    pixels = list(region.getdata())
    dark = sum(
        max(rgb) < 145 and max(rgb) - min(rgb) < 70
        for rgb in pixels
    ) / len(pixels)
    white = sum(min(rgb) > 225 for rgb in pixels) / len(pixels)
    return dark > 0.05 and white > 0.60

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    args = parser.parse_args()

    started = time.monotonic()
    device = u2.connect(args.serial)

    package = CONFIG["package"]
    keyword = CONFIG["keyword"]
    # coords = CONFIG["coordinates"]
    timing = CONFIG["timing"]

    if device.app_current().get("package") != package:
        raise RuntimeError("Baidu is not foreground")

    print("[baidu] 01 open_search", flush=True)
    search_box = device(
        packageName=package,
        className="android.widget.LinearLayout",
        clickable=True,
    )
    if search_box.count != 1:
        raise RuntimeError(
            f"Expected one home search box, found {search_box.count}"
        )
    search_box.click()

    print("[baidu] 02 input_keyword", flush=True)
    field = device(
        packageName=package, className="android.widget.EditText"
    )
    if not field.wait(timeout=2):
        raise RuntimeError("Search input not found")
    field.set_text(keyword)
    print("[baidu] field readback:", repr(field.get_text()), flush=True)

    print("[baidu] 03 submit_search", flush=True)
    submit = device(
        text="搜索", className="android.widget.TextView", clickable=True
    )
    if not submit.wait(timeout=2):
        raise RuntimeError("Submit button not found")
    submit.click()

    result_title = device(
        text=keyword, className="android.widget.TextView"
    )
    if not result_title.wait(timeout=2):
        raise RuntimeError("Result page not reached")

    deadline = time.monotonic() + timing["result_timeout"]
    while not result_body_visible(device):
        if time.monotonic() >= deadline:
            raise RuntimeError("Result body did not appear")
        time.sleep(0.2)

    print("[baidu] 04 return_to_home", flush=True)
    width, height = device.window_size()
    device.swipe(
        max(1, int(width * 0.01)), int(height * 0.5),
        int(width * 0.65), int(height * 0.5),
        duration=0.2,
    )
    if not (
        device(text="百度").wait(timeout=timing["home_timeout"])
        and device(text="我的").exists
    ):
        raise RuntimeError("One right swipe did not return to Baidu home")

    total = time.monotonic() - started

    print(
        json.dumps(
            {
                "app": "baidu",
                "package": package,
                "status": "PASS",
                "keyword": keyword,
                "steps": [
                    {"name": "open_search", "status": "PASS"},
                    {
                        "name": "input_keyword",
                        "status": "PASS",
                        "detail": {"value": keyword}
                    },
                    {
                        "name": "submit_search",
                        "status": "PASS",
                        "detail": {
                            "result_body_visible": True
                        }
                    },
                    {
                        "name": "return_to_home",
                        "status": "PASS",
                        "detail": {"swipe_count": 1}
                    }
                ],
                "elapsed_seconds": round(total, 3)
            },
            ensure_ascii=False,
            indent=2
        )
    )


if __name__ == "__main__":
    main()