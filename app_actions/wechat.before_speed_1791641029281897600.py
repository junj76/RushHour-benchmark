import argparse, json, re, time
from pathlib import Path
import cv2, numpy as np, uiautomator2 as u2
from rapidocr_onnxruntime import RapidOCR

parser = argparse.ArgumentParser()
parser.add_argument("--serial", default="2MN0224119000036")
args = parser.parse_args()
config = json.loads((Path(__file__).parent / "profiles/wechat.json").read_text(encoding="utf-8"))
def name_key(value):
    return re.sub(r"[^\w]", "", value.casefold())

target_name = name_key(config["ocr_contact_text"])
if not target_name or config.get("message") != "hi":
    raise RuntimeError("Configure a contact name; message must be hi")
d = u2.connect(args.serial)
ocr = RapidOCR()
w, h = d.window_size()
home = {"\u5fae\u4fe1", "\u901a\u8baf\u5f55", "\u53d1\u73b0", "\u6211"}
def screen():
    if d.app_current().get("package") != "com.tencent.mm":
        raise RuntimeError("WeChat is not foreground")
    im = d.screenshot().convert("RGB")
    if im.size != (w, h):
        raise RuntimeError("Screen size changed")
    return np.asarray(im)
def read(im, region=None):
    offset = np.array([0, 0])
    if region is not None:
        height, width = im.shape[:2]
        x0, y0, x1, y1 = [
            int(v * size)
            for v, size in zip(region, (width, height, width, height))
        ]
        im = im[y0:y1, x0:x1]
        offset = np.array([x0, y0])
    rows, _ = ocr(im[:, :, ::-1].copy())
    return [
        (np.asarray(b) + offset, re.sub(r"\s+", "", t))
        for b, t, s in rows or [] if s >= 0.5
    ]
def find(predicate, region=None, ready=None):
    deadline = time.monotonic() + 10
    while True:
        rows = read(screen(), region)
        hits = [b for b, t in rows if predicate(b, t)]
        if len(hits) == 1 and (ready is None or ready(hits[0], rows)):
            return hits[0]
        if time.monotonic() >= deadline:
            raise RuntimeError("Target absent or ambiguous: " + str([t for _, t in rows]))
        time.sleep(0.5)
def tap(b):
    x, y = b.mean(axis=0)
    d.click(int(x), int(y))
rows = read(screen(), (0, .8, 1, 1))
if home.issubset({t for _, t in rows}):
    x, y = int(w * .18), int(h * .10)
    crop = cv2.resize(screen()[y:int(h * .85), x:int(w * .65)], None, fx=2, fy=2)
    _, mask = cv2.threshold(cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY), 100, 255, cv2.THRESH_BINARY)
    hits = []
    for im in (crop, cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB)):
        hits = [b for b, t in read(im) if name_key(t) == target_name]
        if len(hits) == 1:
            break
    if len(hits) != 1:
        raise RuntimeError("Contact not uniquely recognized; nothing sent")
    tap(hits[0] / 2 + np.array([x, y]))
find(lambda b, t: name_key(t) == target_name and b[:, 1].mean() < h * .25)
_, mask = cv2.threshold(cv2.cvtColor(screen(), cv2.COLOR_RGB2GRAY), 250, 255, cv2.THRESH_BINARY)
contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
fields = [(x, y, a, b) for x, y, a, b in map(cv2.boundingRect, contours) if .35*w < a < .8*w and .015*h < b < .08*h and x > .07*w and x+a < .85*w and y+b/2 > .8*h]
if len(fields) != 1:
    raise RuntimeError("Input rectangle absent or ambiguous")
x, y, a, b = fields[0]
tap(np.array([[x, y], [x+a, y+b]]))
time.sleep(1)
response = d.shell(["input", "text", "hi"])
if response.exit_code != 0:
    raise RuntimeError("Input failed: " + response.output)
find(lambda b, t: t == name_key(t) == target_name and b[:, 1].mean() < h * .25)
send = find(
    lambda b, t: t == "\u53d1\u9001" and b[:, 1].mean() > h * .5,
    region=(0, .45, 1, .98),
    ready=lambda button, rows: any(
        t == "hi"
        and b[:, 0].max() < button[:, 0].min()
        and b[:, 1].min() < button[:, 1].max()
        and b[:, 1].max() > button[:, 1].min()
        for b, t in rows
    ),
)
find(lambda b, t: t == "hi" and b[:, 1].min() < send[:, 1].max() and b[:, 1].max() > send[:, 1].min())
tap(send)
print("Send clicked once; no automatic resend")
try:
    deadline = time.monotonic() + 10
    while True:
        rows = read(screen())
        outgoing = any(t == "hi" and b[:, 0].mean() > w * .5
                       for b, t in rows)
        send_visible = any(t == "\u53d1\u9001" for _, t in rows)
        if outgoing and not send_visible:
            print("Outgoing hi visible; compose cleared; delivery unverified")
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("Send outcome uncertain; do not resend")
        time.sleep(.5)
finally:
    for count in range(7):
        rows = read(screen())
        bottom = {t for b, t in rows if b[:, 1].mean() > h * .8}
        if home.issubset(bottom):
            print("Returned to WeChat home")
            break
        if count == 6:
            raise RuntimeError("Return home not verified")
        d.press("back")
        time.sleep(1)