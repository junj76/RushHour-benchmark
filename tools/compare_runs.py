#!/usr/bin/env python3
"""Compare RushHour benchmark runs by reading logs/*/summary.txt.

Usage:
  python3 tools/compare_runs.py                      # one row per run, curated metrics
  python3 tools/compare_runs.py --report logs/report.md   # write a Markdown report
  python3 tools/compare_runs.py --full               # every key in every summary
  python3 tools/compare_runs.py --csv out.csv        # flat CSV dump

Conventions:
- Grouped by config.appSet: different app sets are not comparable.
- The scheme label comes from the run id suffix, never from config.swapType.
- 0-byte summary.txt means the run was aborted (the summary is written at the end); they are listed
  and skipped.
- bd_stat counters live in sample.csv, not in summary.txt, so writeback effectiveness is not judged
  here.
- compr.* for zramWriteback runs is missing in historical data (an old code path wrote engine=none);
  re-run those configs to get compression numbers.
"""
import argparse
import csv
import pathlib
import re
import statistics
import sys

DATE_PREFIX = re.compile(r"^\d{8}_\d{6}_")
APP_SET_PREFIX = re.compile(r"^(light|middle|heavy)_")
PERCENT = re.compile(r"\(([\d.]+)%\)")

COLUMNS = [
    ("scheme", None),
    ("sizeMiB", "config.flashSwapMiB"),
    ("wbS", "config.writebackIntervalSec"),
    ("samples", "run.sampleCount"),
    ("launch", "launch.total"),
    ("cold", "launch.cold"),
    ("warm", "launch.warm"),
    ("hot", "launch.hot"),
    ("avgMs", "latency.avgValidMs"),
    ("p50Ms", "latency.p50Ms"),
    ("p95Ms", "latency.p95Ms"),
    ("maxMs", "latency.maxMs"),
    ("coldMs", "latency.coldAvgMs"),
    ("warmMs", "latency.warmAvgMs"),
    ("hotMs", "latency.hotAvgMs"),
    ("alive", "survival.originalAlive"),
    ("running", "survival.currentlyRunning"),
    ("lmkdKills", "mem.lmkdKills"),
    ("psiFull%", "mem.psiFullPctOfRuntime"),
    ("swapIns", "swap.totalSwapIns"),
    ("avgInUs", "swap.avgInLatUs"),
    ("p99InUs", "swap.p99InLatUs"),
    ("comprEngine", "compr.engine"),
    ("comprRatio", "compr.ratio"),
    ("socAvgC", "thermal.socAvgC"),
    ("socMaxC", "thermal.socMaxC"),
]

# metric -> (summary key, higher_is_better)
RANKED = [
    ("launch avg (ms)", "latency.avgValidMs", False),
    ("launch p95 (ms)", "latency.p95Ms", False),
    ("cold avg (ms)", "latency.coldAvgMs", False),
    ("surviving apps (%)", "survival.originalAlive", True),
    ("lmkd kills", "mem.lmkdKills", False),
    ("psi full (%)", "mem.psiFullPctOfRuntime", False),
    ("soc avg (°C)", "thermal.socAvgC", False),
]


# Canonical order == the order summary.txt writes: run -> config -> result -> launch -> latency
# -> survival -> memory -> swap -> compression -> thermal. Inside launch it follows the launch
# lifecycle (cold -> warm -> hot -> unknown -> other -> total), then the diagnostics.
PREFERRED_ORDER = [
    "run.id",
    "run.logsPath",
    "config.seed",
    "config.appSet",
    "config.appOrder",
    "config.swapType",
    "config.flashSwapMiB",
    "config.writebackIntervalSec",
    "config.zswapMaxPoolPercent",
    "config.testRounds",
    "config.sampleIntervalMs",
    "config.launchIntervalMs",
    "config.collectDelayMs",
    "config.swapLabel",
    "config.zramBackingAction",
    "config.zramBackingDevice",
    "config.zramBackingMiB",
    "run.durationMs",
    "run.sampleCount",
    "launch.cold",
    "launch.warm",
    "launch.hot",
    "launch.unknown",
    "launch.other",
    "launch.total",
    "launch.valid",
    "launch.failed",
    "launch.unknownRaw",
    "latency.avgMs",
    "latency.avgValidMs",
    "latency.p50Ms",
    "latency.p95Ms",
    "latency.p99Ms",
    "latency.maxMs",
    "latency.coldAvgMs",
    "latency.warmAvgMs",
    "latency.hotAvgMs",
    "render.jankAvgPct",
    "render.jankMaxPct",
    "render.p50Ms",
    "render.p90Ms",
    "render.p95Ms",
    "render.p99Ms",
    "pss.avgKb",
    "pss.maxKb",
    "survival.originalAlive",
    "survival.currentlyRunning",
    "mem.lmkdKills",
    "mem.lmkdKillsPerMin",
    "mem.psiSomeMs",
    "mem.psiSomePctOfRuntime",
    "mem.psiFullMs",
    "mem.psiFullPctOfRuntime",
    "swap.totalSwapIns",
    "swap.sampledSwapIns",
    "swap.avgInLatUs",
    "swap.p90InLatUs",
    "swap.p99InLatUs",
    "swap.maxInLatUs",
    "swap.inKb",
    "swap.outKb",
    "swap.flashReadsKb",
    "swap.flashWritesKb",
    "compr.engine",
    "compr.ratio",
    "compr.uncompressedMiB",
    "compr.compressedMiB",
    "compr.ramSavedMiB",
    "compr.poolRamAvgMiB",
    "compr.poolRamMaxMiB",
    "thermal.bigAvgC",
    "thermal.midAvgC",
    "thermal.littleAvgC",
    "thermal.socAvgC",
    "thermal.skinAvgC",
    "thermal.socStartC",
    "thermal.socEndC",
    "thermal.socMaxC",
    "thermal.skinStartC",
    "thermal.skinEndC",
]


def key_order(runs):
    """Column order for raw summary keys: follow the writer's own section/key order.

    parse_summary keeps insertion order, so the newest summary dictates the layout (it is written by
    the current code, e.g. launch.cold -> warm -> hot -> unknown -> other -> total). Keys that only
    appear in older files are appended afterwards so nothing is dropped.
    """
    every_key = {k for _, values in runs for k in values}
    order, seen = [], set()
    for key in PREFERRED_ORDER:
        if key in every_key:
            order.append(key)
            seen.add(key)
    for _, values in sorted(runs, key=lambda pair: pair[0], reverse=True):
        for key in values:
            if key not in seen:
                seen.add(key)
                order.append(key)
    return order


def parse_summary(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("[") or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    # Older summaries used launch.otherStates for the same field; normalise the name so both write
    # styles land in one column and the canonical order below can place it.
    if "launch.otherStates" in values:
        values.setdefault("launch.other", values.pop("launch.otherStates"))
    return values


def scheme_from_run_id(run_id):
    return DATE_PREFIX.sub("", run_id)


def family_from_run_id(run_id):
    name = APP_SET_PREFIX.sub("", DATE_PREFIX.sub("", run_id))
    return re.match(r"[A-Za-z]+", name).group(0) if re.match(r"[A-Za-z]+", name) else name


def number(value):
    if value is None:
        return None
    match = PERCENT.search(value)
    if match:
        return float(match.group(1))
    try:
        return float(value)
    except ValueError:
        return None


def collect(logs):
    runs, skipped = [], []
    summary_files = sorted(pathlib.Path(logs).glob("*/summary.txt"))
    if not summary_files:
        # 兼容改动前的目录
        summary_files = sorted(pathlib.Path(logs).glob("*/summary.txt"))
    for summary in summary_files:
        run_id = summary.parent.name
        if summary.stat().st_size == 0:
            skipped.append(run_id)
            continue
        values = parse_summary(summary)
        if not values:
            skipped.append(run_id)
            continue
        runs.append((run_id, values))
    return runs, skipped


def markdown_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    out += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return out


def build_report(runs, skipped, app_set):
    lines = []
    members = [(r, v) for r, v in runs if v.get("config.appSet") == app_set]
    lines.append("### Runs (%s, app set %s)" % (len(members), app_set))
    lines.append("")
    header = [label for label, _ in COLUMNS]
    rows = []
    for run_id, values in members:
        row = []
        for label, key in COLUMNS:
            row.append(scheme_from_run_id(run_id) if key is None else values.get(key, "-"))
        rows.append(row)
    lines += markdown_table(header, rows)
    lines.append("")

    lines.append("### Rankings (single run per config, so ordering is indicative only)")
    lines.append("")
    for label, key, higher_better in RANKED:
        scored = [(number(v.get(key)), scheme_from_run_id(r)) for r, v in members]
        scored = [(s, n) for s, n in scored if s is not None]
        scored.sort(key=lambda pair: pair[0], reverse=higher_better)
        if not scored:
            continue
        formatted = ", ".join(
            "%s %s" % (name, ("%.0f" % score) if abs(score) >= 10 else ("%.2f" % score))
            for score, name in scored[:3]
        )
        lines.append("- **%s** — %s" % (label, formatted))
    lines.append("")

    lines.append("### By scheme family")
    lines.append("")
    families = {}
    for run_id, values in members:
        families.setdefault(family_from_run_id(run_id), []).append(values)
    rows = []
    for family in sorted(families):
        group = families[family]
        avg = [n for n in (number(v.get("latency.avgValidMs")) for v in group) if n is not None]
        kills = [n for n in (number(v.get("mem.lmkdKills")) for v in group) if n is not None]
        alive = [n for n in (number(v.get("survival.originalAlive")) for v in group) if n is not None]
        ratio = [n for n in (number(v.get("compr.ratio")) for v in group) if n is not None]
        rows.append([
            family,
            len(group),
            "%.0f" % statistics.mean(avg) if avg else "-",
            "%.0f" % statistics.mean(kills) if kills else "-",
            "%.1f" % statistics.mean(alive) if alive else "-",
            "%.3f" % statistics.mean(ratio) if ratio else "-",
        ])
    lines += markdown_table(["family", "runs", "avg launch (ms)", "lmkd kills", "surviving (%)", "compr ratio"], rows)
    lines.append("")

    if skipped:
        lines.append("### Skipped runs (0-byte summary = aborted)")
        lines.append("")
        lines += ["- `%s`" % name for name in skipped]
        lines.append("")
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs", default="logs")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--csv", default=None)
    parser.add_argument("--report", default=None)
    parser.add_argument("--app-set", default=None)
    args = parser.parse_args()

    runs, skipped = collect(args.logs)
    if not runs:
        sys.exit("no non-empty summary.txt found under %s/" % args.logs)

    app_sets = sorted({v.get("config.appSet", "?") for _, v in runs})
    if args.app_set is not None:
        app_sets = [s for s in app_sets if s == args.app_set]

    if args.report:
        report = ["# RushHour benchmark comparison", "",
                  "Generated by `tools/compare_runs.py` from `%s/*/summary.txt`." % args.logs, ""]
        for app_set in app_sets:
            report.append("## App set %s" % app_set)
            report.append("")
            report += build_report(runs, skipped, app_set)
        report += [
            "## Reading notes",
            "",
            "- Every configuration has **one** run here, so differences are indicative, not significant.",
            "- `compr.*` is missing for `zramWriteback` runs: an older code path reported engine=none,",
            "  so re-run those configs to get compression numbers.",
            "- Backing-device counters (`bd_stat`) are only in `sample.csv`; writeback effectiveness must",
            "  be judged from `zramBdWrites(KB)` there.",
            "- Scheme names come from the run directory suffix, independent of `config.swapType`.",
            "",
        ]
        pathlib.Path(args.report).write_text("\n".join(report), encoding="utf-8")
        print("wrote %s" % args.report)
        return

    for app_set in app_sets:
        print()
        print("## app set %s" % app_set)
        print()
        if args.full:
            members = [(r, v) for r, v in runs if v.get("config.appSet") == app_set]
            keys = key_order(members)
            print("\n".join(markdown_table(["metric"] + [scheme_from_run_id(r) for r, _ in members],
                                           [[k] + [v.get(k, "-") for _, v in members] for k in keys])))
        else:
            print("\n".join(build_report(runs, skipped, app_set)))

    if args.csv:
        # 纯合并：列 = 所有 summary.txt 里出现过的键（按规范顺序），行 = 每个 run 一个。
        # 不产生任何派生列；缺失键统一写 "-"，保证没有空白单元格。
        keys = key_order(runs)
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            # 只加三个标识列（runId/scheme/status）；run.id、run.logsPath 已在 keys 里。
            # 其余一律照抄 summary.txt，不生成任何派生列，避免右侧重复一遍同样的信息。
            writer.writerow(["runId", "scheme", "status"] + keys)
            for run_id, values in runs:
                writer.writerow(
                    [run_id, scheme_from_run_id(run_id), "ok"]
                    + [values.get(k, "-") for k in keys]
                )
            for run_id in skipped:
                writer.writerow(
                    [run_id, scheme_from_run_id(run_id), "aborted"]
                    + ["-"] * len(keys)
                )

if __name__ == "__main__":
    main()
