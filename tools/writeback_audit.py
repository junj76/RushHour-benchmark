#!/usr/bin/env python3
"""Audit how much zRAM writeback actually happened in each zramWriteback run.

Why: summary.txt has no bd_stat, so "the backing device got bigger but hot launches did not rise"
cannot be explained without knowing how many pages were really written back. sample.csv has the
per-sample bd counters, so this script derives:

  * writeback volume  = last zramBdWrites - first zramBdWrites
  * backend fill      = last zramBdCount / (config.flashSwapMiB * 1024 KB)
  * measurement span  = last - first sampleStamp

Both column naming conventions are handled: older CSVs store the raw 4 KiB counters with a
"(4KB)" header, newer ones store KB with a "(KB)" header (raw * 4).
"""
import csv
import pathlib
import re
import sys

BD_COUNT = re.compile(r"^zramBdCount\((KB|4KB)\)$")
BD_WRITES = re.compile(r"^zramBdWrites\((KB|4KB)\)$")


def parse_summary(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("["):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def scale(unit):
    # Header unit -> factor to KB.
    return 4 if unit == "4KB" else 1


def last_and_first(csv_path):
    with csv_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return None
        count_col = next((n for n in reader.fieldnames if BD_COUNT.match(n)), None)
        writes_col = next((n for n in reader.fieldnames if BD_WRITES.match(n)), None)
        stamp_col = reader.fieldnames[0]
        if count_col is None or writes_col is None:
            return None
        count_factor = scale(BD_COUNT.match(count_col).group(1))
        writes_factor = scale(BD_WRITES.match(writes_col).group(1))
        first = last = None
        rows = 0
        for row in reader:
            rows += 1
            values = (
                int(row[stamp_col]),
                int(float(row[count_col])) * count_factor,
                int(float(row[writes_col])) * writes_factor,
            )
            first = first or values
            last = values
        if rows == 0:
            return None
        return {
            "unit": BD_COUNT.match(count_col).group(1),
            "rows": rows,
            "spanS": (last[0] - first[0]) / 1000.0,
            "writesDeltaKb": last[2] - first[2],
            "countLastKb": last[1],
            "writesLastKb": last[2],
        }


def main():
    logs = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "logs")
    rows = []
    for summary in sorted(logs.glob("*/summary.txt")):
        run_id = summary.parent.name
        if "zramWriteback" not in run_id or summary.stat().st_size == 0:
            continue
        values = parse_summary(summary)
        stats = last_and_first(summary.parent / "sample.csv")
        if stats is None:
            rows.append([run_id, values.get("config.flashSwapMiB", "?"), "?", "-", "-", "-", "-", values.get("launch.hot", "-")])
            continue
        backend_kb = int(values.get("config.flashSwapMiB", "0")) * 1024
        fill = (stats["countLastKb"] / backend_kb * 100.0) if backend_kb else 0.0
        rows.append([
            run_id,
            values.get("config.flashSwapMiB", "?"),
            values.get("config.writebackIntervalSec", "?"),
            "%.1f" % (stats["writesDeltaKb"] / 1024.0),
            "%.1f" % (stats["countLastKb"] / 1024.0),
            "%.1f%%" % fill,
            "%.0f" % stats["spanS"],
            values.get("launch.hot", "-"),
            values.get("mem.lmkdKills", "-"),
            values.get("latency.avgValidMs", "-"),
        ])

    header = ["run", "sizeMiB", "wbS", "bd written (MiB)", "bdCount last (MiB)", "fill%", "span (s)", "hot", "lmkdKills", "avgMs"]
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for row in rows:
        print("| " + " | ".join(str(c) for c in row) + " |")


if __name__ == "__main__":
    main()
