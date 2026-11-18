#!/usr/bin/env python3
"""Compare how much data sits in the zpool under zram vs zswap.

Both schemes use zsmalloc + lz4 here, so compression behaves the same; what can differ is

  * how many pages may enter the pool at all, and
  * whether anything ever leaves it again.

For every run this prints peak values of:
  zram  : zramMemUsedTotal (compressed pool bytes), zramOrigDataSize (uncompressed input)
  zswap : zswapPoolTotalSize (compressed pool bytes), zswapStoredSize  (uncompressed input)
plus meminfoSwapTotal, which is the hard cap on how many swap slots exist.
"""
import csv
import pathlib
import sys

ZRAM_USED = "zramMemUsedTotal(KB)"
ZRAM_ORIG = "zramOrigDataSize(KB)"
ZSWAP_POOL = "zswapPoolTotalSize(KB)"
ZSWAP_STORED = "zswapStoredSize(KB)"
SWAP_TOTAL = "meminfoSwapTotal"


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


def peaks(csv_path):
    with csv_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        wanted = [n for n in (ZRAM_USED, ZRAM_ORIG, ZSWAP_POOL, ZSWAP_STORED, SWAP_TOTAL) if n in fields]
        if not wanted:
            return None
        top = {n: 0.0 for n in wanted}
        for row in reader:
            for name in wanted:
                top[name] = max(top[name], float(row[name] or 0))
        return top


def scheme(run_id):
    for token in ("noSwap", "onlyZram", "zramWriteback", "flashSwap", "zswap"):
        if token in run_id:
            return token
    return "?"


def main():
    logs = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "logs")
    header = ["run", "scheme", "swapTotal (MiB)", "pool compressed peak (MiB)",
              "uncompressed peak (MiB)", "pool / uncompressed", "uncompressed / swapTotal", "compr.ratio"]
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for summary_path in sorted(logs.glob("*/summary.txt")):
        run_id = summary_path.parent.name
        if summary_path.stat().st_size == 0:
            continue
        name = scheme(run_id)
        if name not in ("onlyZram", "zswap", "zramWriteback"):
            continue
        values = parse_summary(summary_path)
        top = peaks(summary_path.parent / "sample.csv")
        if not top:
            continue
        if name == "zswap":
            pool = top.get(ZSWAP_POOL, 0.0)
            uncompressed = top.get(ZSWAP_STORED, 0.0)
        else:
            pool = top.get(ZRAM_USED, 0.0)
            uncompressed = top.get(ZRAM_ORIG, 0.0)
        swap_total = top.get(SWAP_TOTAL, 0.0)
        print("| %s | %s | %.0f | %.0f | %.0f | %.3f | %.3f | %s |" % (
            run_id, name, swap_total / 1024.0, pool / 1024.0, uncompressed / 1024.0,
            (pool / uncompressed) if uncompressed else 0.0,
            (uncompressed / swap_total) if swap_total else 0.0,
            values.get("compr.ratio", "-"),
        ))


if __name__ == "__main__":
    main()
