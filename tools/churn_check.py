#!/usr/bin/env python3
"""Check whether zRAM writeback actually relieved memory, per run.

For each zramWriteback run this prints, from sample.csv:
  * zram pool usage (zramMemUsedTotal) first / last / peak in MiB
  * writeback volume and rate (zramBdWrites delta)
  * PSI full percentage of runtime (from summary.txt), i.e. real memory stall

Rationale: bdCount only says how much fits on the backend, which is capped by the backend size; it
does NOT say how much RAM stayed free. Comparing the zram pool trend against the writeback volume is
what distinguishes "tiering" (pool shrinks, memory relieved) from "thrashing" (pool refills, writeback
only adds I/O).
"""
import csv
import pathlib
import re
import sys

COUNTER = re.compile(r"^zramBdWrites\((KB|4KB)\)$")
POOL = re.compile(r"^zramMemUsedTotal\((KB|4KB)\)$")


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
        stamp = fields[0]
        writes = next((n for n in fields if COUNTER.match(n)), None)
        pool = next((n for n in fields if POOL.match(n)), None)
        if writes is None or pool is None:
            return None
        wf = 4 if COUNTER.match(writes).group(1) == "4KB" else 1
        pf = 4 if POOL.match(pool).group(1) == "4KB" else 1
        pool_values, first_stamp, last_stamp = [], None, None
        first_writes = last_writes = None
        for row in reader:
            if first_stamp is None:
                first_stamp = int(row[stamp])
                first_writes = int(float(row[writes])) * wf
            last_stamp = int(row[stamp])
            last_writes = int(float(row[writes])) * wf
            pool_values.append(int(float(row[pool])) * pf)
        if not pool_values:
            return None
        return {
            "minutes": (last_stamp - first_stamp) / 60000.0,
            "pool_first": pool_values[0] / 1024.0,
            "pool_last": pool_values[-1] / 1024.0,
            "pool_peak": max(pool_values) / 1024.0,
            "written": (last_writes - first_writes) / 1024.0,
        }


def main():
    logs = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "logs")
    header = ["run", "sizeMiB", "min", "pool first (MiB)", "pool peak (MiB)", "pool last (MiB)",
              "written (MiB)", "write MiB/min", "psiFull%", "hot"]
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for summary_path in sorted(logs.glob("*/summary.txt")):
        run_id = summary_path.parent.name
        if "zramWriteback" not in run_id or summary_path.stat().st_size == 0:
            continue
        values = parse_summary(summary_path)
        stats = scan(summary_path.parent / "sample.csv")
        if stats is None:
            continue
        rate = stats["written"] / stats["minutes"] if stats["minutes"] else 0
        print("| %s | %s | %.0f | %.0f | %.0f | %.0f | %.0f | %.1f | %s | %s |" % (
            run_id, values.get("config.flashSwapMiB", "?"), stats["minutes"],
            stats["pool_first"], stats["pool_peak"], stats["pool_last"],
            stats["written"], rate,
            values.get("mem.psiFullPctOfRuntime", "-"), values.get("launch.hot", "-"),
        ))


if __name__ == "__main__":
    main()
