#!/usr/bin/env python3
"""Estimate the CPU cost of zram/zswap compression from existing runs.

Why this works without a profiler:
  * zram compresses in the caller's context (faulting task or kswapd) and zswap does the same plus
    decompression on swap-in, so all of that CPU is accounted as *system* time (vmstat `sy`).
  * sample.csv already records `vmstatUs/Sy` (percent, 1 s window) and `vmstatSi/So` (pages/s),
    so a pooled regression  sy = a + b * (si + so)  gives the marginal system-CPU cost per page/s.
  * b (% of one CPU per page/s) converts to microseconds per page: b/100 s * 1e6 us = b*1e4 us.

Limits: b is a *marginal* estimate over runs that differ in more than swap volume (different apps
alive, different kills), so treat it as +-50%. It separates zram/zswap cost from "no swap" runs only
through the slope, not by direct attribution.
"""
import csv
import pathlib
import sys

SCHEMES = ("noSwap", "onlyZram", "zramWriteback", "flashSwap", "zswap")


def scheme_of(run_id):
    for token in SCHEMES:
        if token in run_id:
            return token
    return "?"


def mean(values):
    return sum(values) / len(values) if values else 0.0


def load(csv_path):
    with csv_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        # column names carry their unit suffix, e.g. vmstatUs/userCpuTime(%) and
        # vmstatSi/swapInBw(MB/s), so match by prefix.
        def find(prefix):
            return next((f for f in fields if f.startswith(prefix)), None)

        c_us, c_sy, c_si, c_so = find("vmstatUs"), find("vmstatSy"), find("vmstatSi"), find("vmstatSo")
        if None in (c_us, c_sy, c_si, c_so):
            return None
        us, sy, si, so = [], [], [], []
        for row in reader:
            us.append(float(row[c_us] or 0))
            sy.append(float(row[c_sy] or 0))
            # si/so are MB/s, not pages/s
            si.append(float(row[c_si] or 0) * 1024.0 / 4.0)
            so.append(float(row[c_so] or 0) * 1024.0 / 4.0)
        if not us:
            return None
        return {"us": mean(us), "sy": mean(sy), "si": mean(si), "so": mean(so), "n": len(us)}


def ols(points):
    n = len(points)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return my, 0.0
    b = sxy / sxx
    return my - b * mx, b


def main():
    logs = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "logs")
    runs = []
    for summary in sorted(logs.glob("*/summary.txt")):
        if summary.stat().st_size == 0:
            continue
        stats = load(summary.parent / "sample.csv")
        if stats is None:
            continue
        runs.append((summary.parent.name, scheme_of(summary.parent.name), stats))
    if not runs:
        sys.exit("no usable sample.csv found")

    points = [(r["si"] + r["so"], r["sy"]) for _, _, r in runs]
    a, b = ols(points)
    us_per_mb = b * 1e4  # %-points per page/s -> microseconds per page

    print("Pooled regression over %d runs:  sy%% = %.2f + %.6f * (si + so)  [pages/s]" % (len(runs), a, b))
    print("  => marginal system-CPU cost per MB swapped: %.0f us/MB (= %.1f us per 4 KiB page)"
          % (us_per_mb / 1024.0, us_per_mb / 1024.0 / 256.0))
    print()
    header = ["run", "scheme", "si pages/s", "so pages/s", "sy%", "us%",
              "compression sy% (model)", "share of sy", "share of us+sy"]
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for run_id, scheme, r in runs:
        rate = r["si"] + r["so"]
        modelled = b * rate
        total = r["us"] + r["sy"]
        print("| %s | %s | %.0f | %.0f | %.1f | %.1f | %.1f | %.0f%% | %.0f%% |" % (
            run_id, scheme, r["si"], r["so"], r["sy"], r["us"], modelled,
            (modelled / r["sy"] * 100.0) if r["sy"] else 0.0,
            (modelled / total * 100.0) if total else 0.0,
        ))
    print()
    print("reading notes")
    print("  * 'compression sy%' is the modelled *marginal* system CPU attributable to swapping")
    print("    (compression + decompression + swap I/O bookkeeping), not a direct per-function measure.")
    print("  * for exact attribution use the kernel's ftrace function profiler while the test runs:")
    print("      echo 0 > /sys/kernel/tracing/function_profile_enabled   # reset")
    print("      echo 1 > /sys/kernel/tracing/function_profile_enabled   # start")
    print("      ... run the benchmark ...")
    print("      cat /sys/kernel/tracing/trace_stat/function0   # zram_bvec_write / lz4_compress / ...")
    print("  * noSwap runs give the regression intercept; they cannot separate compress vs decompress.")


if __name__ == "__main__":
    main()
