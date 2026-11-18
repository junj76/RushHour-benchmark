#!/usr/bin/env python3
"""Audit zswap activity per run: pool usage, limit hits, and write-back volume.

zswap keeps compressed pages in RAM and only writes them to the swap device when the pool cannot
hold them (or when the shrinker reclaims). So "write-back is tiny" is either (a) the pool never
filled up, or (b) the counters are unreadable. This script separates those two cases:

  * pool peak as a fraction of MemTotal tells whether the pool was anywhere near its cap
  * pool_limit_hit tells whether zswap ever refused a page
  * written_back_* tells how many pages were actually pushed to the flash swap file
"""
import csv
import pathlib
import sys

WANTED = ("zswapStoredPages", "zswapStoredSize(KB)", "zswapPoolTotalSize(KB)",
          "zswapPoolLimitHit", "zswapWrittenBackPages", "zswapWrittenBackSize(KB)",
          "meminfoMemTotal")


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


def scan(csv_path):
    with csv_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        cols = {name: next((f for f in fields if f == name), None) for name in WANTED}
        if cols["zswapStoredPages"] is None:
            return None
        stamps = fields[0]
        acc = {name: [] for name in WANTED if cols[name]}
        for row in reader:
            for name, col in cols.items():
                if col:
                    acc[name].append(float(row[col] or 0))
        if not acc["zswapStoredPages"]:
            return None
        return acc


def main():
    logs = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "logs")
    header = ["run", "sizeMiB", "memTotal (MiB)", "pool peak (MiB)", "pool peak / RAM",
              "stored peak (MiB)", "limit hits", "written back (pages)", "written back (MiB)", "hot"]
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for summary_path in sorted(logs.glob("*/summary.txt")):
        run_id = summary_path.parent.name
        if "zswap" not in run_id or summary_path.stat().st_size == 0:
            continue
        values = parse_summary(summary_path)
        acc = scan(summary_path.parent / "sample.csv")
        if acc is None:
            continue
        mem_total = max(acc["meminfoMemTotal"]) / 1024.0 if acc.get("meminfoMemTotal") else 0.0
        pool_peak = max(acc["zswapPoolTotalSize(KB)"]) / 1024.0
        stored_peak = max(acc["zswapStoredSize(KB)"]) / 1024.0
        hits = max(acc["zswapPoolLimitHit"]) if acc.get("zswapPoolLimitHit") else 0
        wb_pages = max(acc["zswapWrittenBackPages"]) if acc.get("zswapWrittenBackPages") else 0
        wb_mib = max(acc["zswapWrittenBackSize(KB)"]) / 1024.0 if acc.get("zswapWrittenBackSize(KB)") else 0.0
        print("| %s | %s | %.0f | %.0f | %.2f%% | %.0f | %.0f | %.0f | %.0f | %s |" % (
            run_id, values.get("config.flashSwapMiB", "?"), mem_total, pool_peak,
            (pool_peak / mem_total * 100.0) if mem_total else 0.0, stored_peak, hits, wb_pages, wb_mib,
            values.get("launch.hot", "-"),
        ))


if __name__ == "__main__":
    main()
