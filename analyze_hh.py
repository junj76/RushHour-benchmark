# 用法: python analyze_hh.py logs/<目录>/sample.csv [extent=32]
#       python analyze_hh.py logs/<目录> [extent=32]  （也接受目录）
#
# 分析 hyperhold 统计 + swap 延迟，结果追加写入 sample.csv 同目录下的 summary.txt
# （不覆盖 gradle 写的内容）
#
# 说明:
#   - hh* 是累计计数器 —— 用「末行 - 首行」得到本轮增量
#   - sl* 是累积统计量（内核 reset 之后累计）——
#     count/sampled 可取差值，mean/p50/p90/p99/max 直接取末行（不可相加）

import csv
import os
import re
import sys

csv_path = sys.argv[1]
if os.path.isdir(csv_path):
    csv_path = os.path.join(csv_path, "sample.csv")

rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
f, l = rows[0], rows[-1]


def parse_extent_kb(value):
    text = value.strip().lower()
    for suffix in ("kib", "kb", "k"):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
            break
    extent_kb = int(text)
    if extent_kb <= 0:
        raise ValueError("extent must be positive")
    return extent_kb


extent_size_kb = None
arg_index = 2
while arg_index < len(sys.argv):
    arg = sys.argv[arg_index]
    if arg.startswith("extent="):
        extent_size_kb = parse_extent_kb(arg.split("=", 1)[1])
    elif arg == "--extent":
        arg_index += 1
        if arg_index >= len(sys.argv):
            raise ValueError("--extent requires a value")
        extent_size_kb = parse_extent_kb(sys.argv[arg_index])
    elif arg.startswith("--extent="):
        extent_size_kb = parse_extent_kb(arg.split("=", 1)[1])
    else:
        raise ValueError("unknown argument: " + arg)
    arg_index += 1

if extent_size_kb is None:
    match = re.search(r"_extent(\d+)k(?:_|$)", os.path.basename(
        os.path.dirname(os.path.abspath(csv_path))
    ))
    if match:
        extent_size_kb = int(match.group(1))
    elif rows and "extentSizeKb" in rows[-1]:
        extent_size_kb = int(float(rows[-1]["extentSizeKb"]))
    else:
        extent_size_kb = 32

EXTENT_SIZE_BYTES = extent_size_kb * 1024

# 输出目标：与 sample.csv 同目录的 summary.txt
summary_path = os.path.join(os.path.dirname(os.path.abspath(csv_path)), "summary.txt")
launch_path = os.path.join(os.path.dirname(os.path.abspath(csv_path)), "launch.csv")


def count_launch_states():
    counts = {"COLD": 0, "WARM": 0, "HOT": 0, "UNKNOWN": 0}
    if os.path.isfile(launch_path):
        with open(launch_path, encoding="utf-8-sig") as launch_file:
            for row in csv.DictReader(launch_file):
                state = (row.get("amStartLaunchState") or "").strip()
                if state in counts:
                    counts[state] += 1
                else:
                    counts["UNKNOWN"] += 1
    if sum(counts.values()) == 0 and os.path.isfile(summary_path):
        text = open(summary_path, encoding="utf-8", errors="ignore").read()
        patterns = {
            "COLD": r"coldLaunchCnt:\s*(\d+)",
            "WARM": r"warmLaunchCNT:\s*(\d+)",
            "HOT": r"hotLaunchCnt:\s*(\d+)",
            "UNKNOWN": r"unknownLaunchCnt:\s*(\d+)",
        }
        for state, pattern in patterns.items():
            found = re.search(pattern, text)
            if found:
                counts[state] = int(found.group(1))
    return counts


launch_counts = count_launch_states()
out_file = open(summary_path, "a", encoding="utf-8")


def out(text=""):
    out_file.write(text + "\n")
    out_file.flush()
    print(text)


def n(r, k):
    try:
        return int(float(r[k]))
    except (KeyError, ValueError, TypeError):
        return 0


def d(k):
    return n(l, k) - n(f, k)


# ===================== 1. hyperhold 统计 =====================
io_cnt, io_bytes = d("hhIoReqCnt"), d("hhIoReqBytes")
avg_obj = io_bytes / max(io_cnt, 1)          # 平均被请求的压缩对象大小（字节）
read_in = d("hhReadInBytes")
# read_req = d("hhUfsReadExtentCnt")
read_req = 0
if read_req <= 0 and read_in > 0:
    read_req = int(round(read_in / max(EXTENT_SIZE_BYTES, 1)))
w_raw, w_ufs = d("hhWriteRawBytes"), d("hhWriteUfsBytes")
# write_req = d("hhUfsWriteExtentCnt")
write_req = 0
if write_req <= 0 and w_ufs > 0:
    write_req = int(round(w_ufs / max(EXTENT_SIZE_BYTES, 1)))
# 与旧内核保持一致，暂时不使用读取到的数据而是使用计数数据
read_batch = d("hhUfsReadBatchCnt")
write_batch = d("hhUfsWriteBatchCnt")
pf, hit, miss = d("hhPfObjs"), d("hhPfHitObjs"), d("hhPfNeverUsedObjs")
peak = max(n(r, "hhInflightPagesPeak") for r in rows)

# hyperhold_cache 占用情况
CACHE_PAGE_BYTES = 4096


def sampled_average(key):
    """
    按采样时间对当前值求平均。
    cache_pages 是瞬时值，不能对累计计数器做差值。
    """
    values = [n(r, key) for r in rows]

    weighted_sum = 0
    total_ms = 0

    for current, next_row in zip(rows, rows[1:]):
        dt = (
            n(next_row, "sampleStamp(ms)")
            - n(current, "sampleStamp(ms)")
        )
        if dt > 0:
            weighted_sum += n(current, key) * dt
            total_ms += dt

    if total_ms > 0:
        return weighted_sum / total_ms

    return sum(values) / max(len(values), 1)


cache_values = [n(r, "hhCachePages") for r in rows]
cache_avg_pages = sampled_average("hhCachePages")
cache_peak_sampled = max(cache_values, default=0)

pf_cache_values = [n(r, "hhPfCachePages") for r in rows]
pf_cache_avg_pages = sampled_average("hhPfCachePages")
pf_cache_peak_sampled = max(pf_cache_values, default=0)



out("")
out("===== 启动统计 =====")
out("实验 extent 大小    : %d KB" % extent_size_kb)
out("冷/温/热/未知启动   : %d / %d / %d / %d"
    % (launch_counts["COLD"], launch_counts["WARM"],
       launch_counts["HOT"], launch_counts["UNKNOWN"]))

out("")
out("===== hyperhold 统计（analyze_hh.py 追加） =====")
out("写入目标文件        : " + summary_path)
out("采样点数            : %d" % len(rows))
out("回抬读入            : %d 字节 = %.0f 个 %dKB extent"
    % (read_in, read_in / EXTENT_SIZE_BYTES, extent_size_kb))
out("下刷写入 UFS        : %d 字节 = %.0f 个 %dKB extent"
    % (w_ufs, w_ufs / EXTENT_SIZE_BYTES, extent_size_kb))
out("HyperHold 读请求    : %d 次, 平均 %.0f 字节/次"
    % (read_req, read_in / max(read_req, 1)))
out("HyperHold 写请求    : %d 次, 平均 %.0f 字节/次"
    % (write_req, w_ufs / max(write_req, 1)))
# out("HyperHold 回抬批次数: %d，下刷批次数: %d"
#     % (read_batch, write_batch))
out("HyperHold 读数据量  : %d 字节" % read_in)
out("HyperHold 写数据量  : %d 字节" % w_ufs)
# out("下刷收集压缩字节    : %d 字节" % w_raw)
# out("写放大              : %.3f" % (w_ufs / max(w_raw, 1)))



dm, dm_hit, dm_never = d("hhPfDemandObjs"), d("hhPfDemandHitObjs"), d("hhPfDemandNeverObjs")
dm_groups = d("hhPfDemandGroups")
avg_group = dm / max(dm_groups, 1)

out("")
out("===== 内存代价 =====")
out("搬回 zram           : %d 字节 / %d 个对象" % (d("hhMovedInBytes"), d("hhMovedInPages")))

# out("在飞缓冲峰值        : %d 页 = %.1f MiB" % (peak, peak * CACHE_PAGE_BYTES / 1024.0 / 1024.0))

out("cache 平均数据区    : %.1f 页 = %.1f MiB" % ( cache_avg_pages, cache_avg_pages * CACHE_PAGE_BYTES / 1024.0 / 1024.0 ))

out("cache 采样峰值      : %d 页 = %.1f MiB"   % ( cache_peak_sampled, cache_peak_sampled * CACHE_PAGE_BYTES / 1024.0 / 1024.0))

# out("应用预热cache平均值 : %.1f 页 = %.1f MiB" % ( pf_cache_avg_pages, pf_cache_avg_pages * CACHE_PAGE_BYTES / 1024.0 / 1024.0))

# out("应用预热cache采样峰值: %d 页 = %.1f MiB" % ( pf_cache_peak_sampled, pf_cache_peak_sampled * CACHE_PAGE_BYTES / 1024.0 / 1024.0 ))

out("")
out("===== extent cache 因后端空间紧张搬回 zpool =====")
cm_exts = d("hhCacheMoveExts")
cm_bytes = d("hhCacheMoveValidBytes")
cm_objs = d("hhCacheMoveValidObjs")
cm_bytes_min = n(l, "hhCacheMoveValidBytesMin")
cm_bytes_max = n(l, "hhCacheMoveValidBytesMax")
cm_objs_min = n(l, "hhCacheMoveValidObjsMin")
cm_objs_max = n(l, "hhCacheMoveValidObjsMax")

# out("口径: 仅统计被 extent_can_move() 选中且完整搬回 zpool 的 extent；")
# out("      有效数据指压缩对象字节数，不是解压后的 4KB 原始页大小")
out("搬回 extent         : %d" % cm_exts)
if cm_exts > 0:
    cm_bytes_avg = cm_bytes / cm_exts
    cm_objs_avg = cm_objs / cm_exts
    cm_util_min = 100.0 * cm_bytes_min / EXTENT_SIZE_BYTES
    cm_util_avg = 100.0 * cm_bytes_avg / EXTENT_SIZE_BYTES
    cm_util_max = 100.0 * cm_bytes_max / EXTENT_SIZE_BYTES
    out("有效压缩数据总量    : %d 字节" % cm_bytes)
    out("每 extent 有效字节 : min %d / avg %.1f / max %d 字节"
        % (cm_bytes_min, cm_bytes_avg, cm_bytes_max))
    # out("每 extent 有效对象 : min %d / avg %.2f / max %d 个"
    #     % (cm_objs_min, cm_objs_avg, cm_objs_max))
    out("%dKB extent 利用率 : min %.1f%% / avg %.1f%% / max %.1f%%"
        % (extent_size_kb, cm_util_min, cm_util_avg, cm_util_max))
    # out("%dKB extent 平均浪费: %.1f 字节"
    #     % (extent_size_kb, EXTENT_SIZE_BYTES - cm_bytes_avg))
else:
    out("有效压缩数据总量    : 0 字节")
    out("每 extent 有效字节 : —（本轮未触发 cache 空间回收搬回）")
    out("每 extent 有效对象 : —（本轮未触发 cache 空间回收搬回）")
    out("%dKB extent 利用率 : —（本轮无样本）" % extent_size_kb)
    out("%dKB extent 平均浪费: —（本轮无样本）" % extent_size_kb)
out("注: min/max 使用内核 reset 后的累计极值；总量与平均值按本轮采样增量计算")

out("")
out("===== 预取（应用预热）=====")
pf_pending = pf - hit - miss
# out("应用预热对象        : %d（命中 %d, 未用 %d, 未结算 %d）" % (pf, hit, miss, pf_pending))
out("应用预热对象        : %d（命中 %d, 未用 %d）"% (pf, hit, miss))
out("应用预热命中率      : %.1f%%（%d / %d）"
    % (100.0 * hit / max(pf, 1), hit, pf))

out("")
out("===== 匿名页寿命（1/64 采样） =====")
out("zram 驻留总量       : %d，已结算采样 %d，分位样本 %d"
    % (n(l, "hhZramLifeTotal"), n(l, "hhZramLifeSampled"),
       n(l, "hhZramLifeRankN")))
out("zram 平均寿命       : %.2f ms"
    % (n(l, "hhZramLifeAvgNs") / 1_000_000.0))
out("zram P10~P90        : %.2f / %.2f / %.2f / %.2f / %.2f / %.2f / %.2f / %.2f / %.2f ms"
    % (n(l, "hhZramLifeP10Ns") / 1_000_000.0,
       n(l, "hhZramLifeP20Ns") / 1_000_000.0,
       n(l, "hhZramLifeP30Ns") / 1_000_000.0,
       n(l, "hhZramLifeP40Ns") / 1_000_000.0,
       n(l, "hhZramLifeP50Ns") / 1_000_000.0,
       n(l, "hhZramLifeP60Ns") / 1_000_000.0,
       n(l, "hhZramLifeP70Ns") / 1_000_000.0,
       n(l, "hhZramLifeP80Ns") / 1_000_000.0,
       n(l, "hhZramLifeP90Ns") / 1_000_000.0,
       ))
out("zram P99            : %.2f ms"
    % (n(l, "hhZramLifeP99Ns") / 1_000_000.0))
out("zram 最大寿命       : %.2f ms"
    % (n(l, "hhZramLifeMaxNs") / 1_000_000.0))
out("zram 结束原因       : 下刷 %d, 读回 %d, 失效/释放 %d"
    % (n(l, "hhZramLifeEndWb"),
       n(l, "hhZramLifeEndReadback"),
       n(l, "hhZramLifeEndFree")))

out("UFS 副本总量        : %d，已结算采样 %d，分位样本 %d"
    % (n(l, "hhUfsLifeTotal"), n(l, "hhUfsLifeSampled"),
       n(l, "hhUfsLifeRankN")))
out("UFS 平均寿命        : %.2f ms"
    % (n(l, "hhUfsLifeAvgNs") / 1_000_000.0))
out("UFS P10~P90         : %.2f / %.2f / %.2f / %.2f / %.2f / %.2f / %.2f / %.2f / %.2f ms"
    % (n(l, "hhUfsLifeP10Ns") / 1_000_000.0,
       n(l, "hhUfsLifeP20Ns") / 1_000_000.0,
       n(l, "hhUfsLifeP30Ns") / 1_000_000.0,
       n(l, "hhUfsLifeP40Ns") / 1_000_000.0,
       n(l, "hhUfsLifeP50Ns") / 1_000_000.0,
       n(l, "hhUfsLifeP60Ns") / 1_000_000.0,
       n(l, "hhUfsLifeP70Ns") / 1_000_000.0,
       n(l, "hhUfsLifeP80Ns") / 1_000_000.0,
       n(l, "hhUfsLifeP90Ns") / 1_000_000.0,
       ))
out("UFS P99             : %.2f ms"
    % (n(l, "hhUfsLifeP99Ns") / 1_000_000.0))
out("UFS 最大寿命        : %.2f ms"
    % (n(l, "hhUfsLifeMaxNs") / 1_000_000.0))
out("UFS 结束原因        : 读回 %d, 失效/释放 %d"
    % (n(l, "hhUfsLifeEndReadback"), n(l, "hhUfsLifeEndFree")))
out("注: P10~P90/P99 基于已保存的原始采样寿命排序，不使用分桶")

out("")
out("===== 预取（缺页触发）=====")
out("按需回抬            : %d 次, %d 字节, 平均 %.0f 字节/次" % (io_cnt, io_bytes, io_bytes / max(io_cnt, 1))) # 发生了几次、每次要多少 只有对象真正在 UFS extent 里、且确实要发 IO 时（hyperhold_fault_out_check() 返回 0）才计数
# out("平均读放大    : %dKB / %.0f 字节 = %.1f 倍（为取 1 个对象读回一整条 extent）"
#    % (extent_size_kb, avg_obj, EXTENT_SIZE_BYTES / max(avg_obj, 1)))
out("预取组数            : %d 组, 平均每组 %.1f 个对象" % (dm_groups, avg_group))  # 读回了几条 extent
out("预取对象            : %d（命中 %d, 未用 %d, 未结算 %d）" % (dm, dm_hit, dm_never, dm - dm_hit - dm_never))  # 这些 extent 里有多少个搭便车读入的对象
out("预取命中率          : %.1f%%（%d / %d）"
    % (100.0 * dm_hit / max(dm, 1), dm_hit, dm))
if dm_groups > 0:
    out("每组平均命中        : %.2f 个/组" % (dm_hit / dm_groups))
else:
    out("每组平均命中        : —（本轮没有预取样本）")

dm_bytes = d("hhPfDemandHitBytes")
demand_read_in = dm_groups * EXTENT_SIZE_BYTES
out("预取命中对象字节    : %d" % dm_bytes)
out("按需回抬读入        : %d 字节（%d 组 × %dKB）"
    % (demand_read_in, dm_groups, extent_size_kb))
# out("读放大(按需·毛)     : %.1f 倍（%d ÷ %d）"
#     % (demand_read_in / max(io_bytes, 1), demand_read_in, io_bytes))
out("读放大     : %.1f 倍（扣掉命中的 %d 字节）"
    % ((demand_read_in - dm_bytes) / max(io_bytes, 1), dm_bytes))

# ===================== 2. swap-in 延迟（fault 端到端，major fault） =====================
if "swLatTotal" in l:
    out("")
    out("===== swap-in 延迟（analyze_hh.py 追加） =====")
    out("口径: do_swap_page 入口 → 页已映射；只统计 MAJOR fault；已过滤 VM_FAULT_RETRY 重入")
    out("统计开关            : %s" % ("on" if n(l, "swLatEnabled") else "off"))

    total, samp = n(l, "swLatTotal"), n(l, "swLatSampled")
    if samp == 0:
        out("--- 无样本（统计未开启，或本轮没有swap-in）---")
    else:
        out("--- swap_in---")
        out("  总换入次数        : %d" % total)
        out("  采样次数          : %d  (%.1f%%)" % (samp, 100.0 * samp / max(total, 1)))
        out("  平均延迟          : %d ns = %.2f us" % (n(l, "swLatAvgNs"), n(l, "swLatAvgNs") / 1000.0))
        out("  P90  延迟         : %d ns = %.2f us" % (n(l, "swLatP90Ns"), n(l, "swLatP90Ns") / 1000.0))
        out("  P99  延迟         : %d ns = %.2f us" % (n(l, "swLatP99Ns"), n(l, "swLatP99Ns") / 1000.0))
        out("  最大延迟          : %d ns = %.2f ms" % (n(l, "swLatMaxNs"), n(l, "swLatMaxNs") / 1000000.0))
        p50_est = n(l, "swLatAvgNs")
        if p50_est and n(l, "swLatP99Ns"):
            out("  P99/avg 比值      : %.1fx" % (n(l, "swLatP99Ns") / float(p50_est)))
    out("  注: p90/p99 是桶上沿（log2+8 子桶，最多高估 12.5%）；avg/max 精确")

    out("")
    out("===== 前台线程 direct reclaim =====")
    dr_total = n(l, "directReclaimTotal")
    dr_fg_total = n(l, "directReclaimFgTotal")
    dr_sampled = n(l, "directReclaimSampled")
    out("direct reclaim 总次数 : %d" % dr_total)
    out("前台线程 direct reclaim: %d 次" % dr_fg_total)
    out("有效用时样本          : %d，分位样本 %d"
        % (dr_sampled, n(l, "directReclaimRankN")))
    if dr_sampled:
        out("平均用时              : %.2f ms"
            % (n(l, "directReclaimAvgNs") / 1_000_000.0))
        out("P10~P90               : %.2f / %.2f / %.2f / %.2f / %.2f / %.2f / %.2f / %.2f / %.2f ms"
            % (n(l, "directReclaimP10Ns") / 1_000_000.0,
               n(l, "directReclaimP20Ns") / 1_000_000.0,
               n(l, "directReclaimP30Ns") / 1_000_000.0,
               n(l, "directReclaimP40Ns") / 1_000_000.0,
               n(l, "directReclaimP50Ns") / 1_000_000.0,
               n(l, "directReclaimP60Ns") / 1_000_000.0,
               n(l, "directReclaimP70Ns") / 1_000_000.0,
               n(l, "directReclaimP80Ns") / 1_000_000.0,
               n(l, "directReclaimP90Ns") / 1_000_000.0,
               ))
        out("P99                   : %.2f ms"
            % (n(l, "directReclaimP99Ns") / 1_000_000.0))
        out("最大用时              : %.2f ms"
            % (n(l, "directReclaimMaxNs") / 1_000_000.0))
    else:
        out("平均/P50/P90/P99/最大 : —（本轮无前台 direct reclaim 样本）")
    out("注: 前台按 cpuset top-app/foreground 并集判定；P50/P90/P99 基于原始耗时排序")
out_file.close()
