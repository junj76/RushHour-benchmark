import argparse
from pathlib import Path

from device_connection import connect_device
from app_ui import visible_ui_packages


parser = argparse.ArgumentParser()
parser.add_argument("--name", required=True)
args = parser.parse_args()

if not args.name.replace("_", "").isalnum():
    parser.error("--name 只能包含字母、数字和下划线")

d = connect_device()
folder = Path(__file__).resolve().parent / "ui_dumps"
folder.mkdir(exist_ok=True)

path = folder / (args.name + ".xml")
ui_xml = d.dump_hierarchy(compressed=False)
path.write_text(
    ui_xml,
    encoding="utf-8",
)

print("界面 XML 中可见的包名：", visible_ui_packages(ui_xml))
print("界面 XML 保存位置：", path)
