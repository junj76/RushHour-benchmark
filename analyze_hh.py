# 用法: python analyze_hh.py logs/<目录>/sample.csv
#       python analyze_hh.py logs/<目录>            （也接受目录）
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
import sys

csv_path = sys.argv[1]
if os.path.isdir(csv_path):
    csv_path = os.path.join(csv_path, "sample.csv")

rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
f, l = rows[0], rows[-1]

# 输出目标：与 sample.csv 同目录的 summary.txt
summary_path = os.path.join(os.path.dirname(os.path.abspath(csv_path)), "summary.txt")
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
w_raw, w_ufs = d("hhWriteRawBytes"), d("hhWriteUfsBytes")
pf, hit, miss = d("hhPfObjs"), d("hhPfHitObjs"), d("hhPfNeverUsedObjs")
peak = max(n(r, "hhInflightPagesPeak") for r in rows)
cache_peak = max(n(r, "hhCachePagesPeak") for r in rows)

out("")
out("===== hyperhold 统计（analyze_hh.py 追加） =====")
out("写入目标文件        : " + summary_path)
out("采样点数            : %d" % len(rows))
out("回抬读入            : %d 字节 = %.0f 个 32KB extent" % (read_in, read_in / 32768))
out("下刷写入 UFS        : %d 字节 = %.0f 个 32KB extent" % (w_ufs, w_ufs / 32768))
out("下刷收集压缩字节    : %d 字节" % w_raw)
out("写放大              : %.3f" % (w_ufs / max(w_raw, 1)))
# out("应用预热对象        : %d（命中 %d, 未用 %d, 未结算 %d）" % (pf, hit, miss, pf - hit - miss))

dm, dm_hit, dm_never = d("hhPfDemandObjs"), d("hhPfDemandHitObjs"), d("hhPfDemandNeverObjs")
dm_groups = d("hhPfDemandGroups")
avg_group = dm / max(dm_groups, 1)


out("===== 内存代价 =====")
out("搬回 zram           : %d 字节 / %d 个对象" % (d("hhMovedInBytes"), d("hhMovedInPages")))
out("在飞缓冲峰值        : %d 页 = %.1f MB" % (peak, peak * 4 / 1024.0))
out("cache 常驻峰值(全量): %d 页" % cache_peak)
# out("cache 常驻峰值(仅应用预热): %d 页" % d("hhPfCachePagesPeak"))

out("")
out("===== 按需回抬 / 预取（缺页触发）=====")
out("按需回抬            : %d 次, %d 字节, 平均 %.0f 字节/次" % (io_cnt, io_bytes, io_bytes / max(io_cnt, 1))) # 发生了几次、每次要多少 只有对象真正在 UFS extent 里、且确实要发 IO 时（hyperhold_fault_out_check() 返回 0）才计数
out("平均读放大    : 32KB / %.0f 字节 = %.1f 倍（为取 1 个对象读回一整条 extent）" 
    % (avg_obj, 32768.0 / max(avg_obj, 1)))
out("预取组数            : %d 组, 平均每组 %.1f 个对象" % (dm_groups, avg_group))  # 读回了几条 extent
out("预取对象            : %d（命中 %d, 未用 %d, 未结算 %d）" % (dm, dm_hit, dm_never, dm - dm_hit - dm_never))  # 这些 extent 里有多少个搭便车读入的对象
out("预取命中率(已结算)  : %.1f%%" % (100.0 * dm_hit / max(dm_hit + dm_never, 1)))
out("预取命中率(占全部)  : %.1f%%" % (100.0 * dm_hit / max(dm, 1)))
if dm_groups > 0:
    out("每组平均命中        : %.2f 个/组（基准 1.00 = 每组只被用掉 1 个）" % (dm_hit / dm_groups))
else:
    out("每组平均命中        : —（本轮没有预取样本）")

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
out_file.close()
