#!/usr/bin/env python3
"""Backfill render/jank/PSS aggregates into existing summaries from each run's launch.csv.

The values are recomputed from the same run's raw per-launch records (launch.csv), using the same
rules the Kotlin code now uses: average over launches for render percentiles and PSS, max for jank and
PSS. This only fills in what the old writer could not emit, and the lines are inserted right after
latency.hotAvgMs so old files look exactly like new ones.
"""
import csv
import pathlib
import sys

LINES = (
    ("render.jankAvgPct", 2),
    ("render.jankMaxPct", 2),
    ("render.p50Ms", 0),
    ("render.p90Ms", 0),
    ("render.p95Ms", 0),
    ("render.p99Ms", 0),
    ("pss.avgKb", 0),
    ("pss.maxKb", 0),
)


def find_column(fields, prefix):
    return next((f for f in fields if f.startswith(prefix)), None)


def main():
    logs = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "logs")
    patched = 0
    skipped = 0
    for summary in sorted(logs.glob("*/summary.txt")):
        run = summary.parent
        launch_csv = run / "launch.csv"
        if summary.stat().st_size == 0 or not launch_csv.exists() or launch_csv.stat().st_size == 0:
            skipped += 1
            continue
        text = summary.read_text(encoding="utf-8")
        if "render.jankAvgPct=" in text:
            skipped += 1
            continue

        with launch_csv.open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames or []
            c_jank = find_column(fields, "jankyFrames")
            c_p50 = find_column(fields, "p50RenderLat")
            c_p90 = find_column(fields, "p90RenderLat")
            c_p95 = find_column(fields, "p95RenderLat")
            c_p99 = find_column(fields, "p99RenderLat")
            c_pss = find_column(fields, "totalPss")
            if not all((c_jank, c_p50, c_p90, c_p95, c_p99, c_pss)):
                print("SKIP %s (columns: %s)" % (run.name, fields))
                skipped += 1
                continue
            jank, p50, p90, p95, p99, pss = [], [], [], [], [], []
            for row in reader:
                try:
                    jank.append(float(row[c_jank]))
                    p50.append(float(row[c_p50]))
                    p90.append(float(row[c_p90]))
                    p95.append(float(row[c_p95]))
                    p99.append(float(row[c_p99]))
                    pss.append(float(row[c_pss]))
                except (TypeError, ValueError):
                    continue

        if not jank:
            skipped += 1
            continue

        def avg(values):
            return int(round(sum(values) / len(values)))

        values = {
            "render.jankAvgPct": "%.2f" % (sum(jank) / len(jank)),
            "render.jankMaxPct": "%.2f" % max(jank),
            "render.p50Ms": avg(p50),
            "render.p90Ms": avg(p90),
            "render.p95Ms": avg(p95),
            "render.p99Ms": avg(p99),
            "pss.avgKb": avg(pss),
            "pss.maxKb": int(max(pss)),
        }

        out = []
        for line in text.splitlines():
            out.append(line)
            if line.startswith("latency.hotAvgMs="):
                for key, _decimals in LINES:
                    out.append("%s=%s" % (key, values[key]))
        summary.write_text("\n".join(out) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
        patched += 1

    print("patched %d summaries, skipped %d" % (patched, skipped))


if __name__ == "__main__":
    main()
