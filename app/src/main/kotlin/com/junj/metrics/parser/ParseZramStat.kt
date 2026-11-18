package com.junj.metrics.parser

data class ZramMmStatResult(
    val origDataSize: Long, //
    val comprDataSize: Long,
    val memUsedTotal: Long,
    val memUsedMax: Long,
)

data class ZramBdStatResult(
    val bdCount: Long,
    val bdReads: Long,
    val bdWrites: Long,
)

fun parseZramMmStatResult(output: String): ZramMmStatResult? {
    val values = output
        .lineSequence()
        .firstOrNull(){ it.isNotEmpty() }
        ?.trim()
        ?.split(Regex("""\s+"""))
        ?: return null

    if (values.size < 9)
        return null

    // 拿到的不是数字（比如设备端返回了一行报错）时返回 null，
    // 不要让一个异常把整个采样线程干掉、导致一个样本都写不出来。
    return runCatching {
        ZramMmStatResult(
            origDataSize = values[0].toLong(),
            comprDataSize = values[1].toLong(),
            memUsedTotal = values[2].toLong(),
            memUsedMax = values[4].toLong()
        )
    }.getOrNull()
}

fun parseZramBdStatResult(output: String): ZramBdStatResult? {
    val values = output
        .lineSequence()
        .firstOrNull(){ it.isNotEmpty() }
        ?.trim()
        ?.split(Regex("""\s+"""))
        ?: return null
    if (values.size < 3)
        return null

    return runCatching {
        ZramBdStatResult(
            bdCount = values[0].toLong(),
            bdReads = values[1].toLong(),
            bdWrites = values[2].toLong(),
        )
    }.getOrNull()
}

data class HyperholdStatResult(
    val ioReqCnt: Long,
    val ioReqBytes: Long,
    val ufsReadReqCnt: Long,
    val ufsWriteReqCnt: Long,
    val ufsReadExtentCnt: Long,
    val ufsWriteExtentCnt: Long,
    val readInBytes: Long,
    val writeRawBytes: Long,
    val writeUfsBytes: Long,
    val faultoutFaultCnt: Long,
    val pfObjs: Long,
    val pfHitObjs: Long,
    val pfNeverUsedObjs: Long,
    val pfNeverUsedBytes: Long,
    val inflightPages: Long,
    val inflightPagesPeak: Long,
    val movedInBytes: Long,
    val movedInPages: Long,
    val cachePages: Long,
    val cachePagesPeak: Long,
    // extent cache 因后端空间紧张而完整搬回 zpool 的统计
    val cacheMoveExts: Long,
    val cacheMoveValidBytes: Long,
    val cacheMoveValidBytesMin: Long,
    val cacheMoveValidBytesMax: Long,
    val cacheMoveValidBytesAvg: Long,
    val cacheMoveValidObjs: Long,
    val cacheMoveValidObjsMin: Long,
    val cacheMoveValidObjsMax: Long,
    val cacheMoveValidObjsAvgX100: Long,
    val cacheMoveUtilAvgX100: Long,
    val cacheMoveUtilMinX100: Long,
    val cacheMoveUtilMaxX100: Long,
        // ===== 新增：按需预取 / 批量预取的 cache 占用 =====
    val pfDemandGroups: Long,
    val pfDemandObjs: Long,
    val pfDemandHitObjs: Long,
    val pfDemandNeverObjs: Long,
    val pfDemandHitBytes: Long,
    val pfCachePages: Long,
    val pfCachePagesPeak: Long,
    val zramLifeTotal: Long,
    val zramLifeSampled: Long,
    val zramLifeRankN: Long,
    val zramLifeAvgNs: Long,
    val zramLifeP10Ns: Long,
    val zramLifeP20Ns: Long,
    val zramLifeP30Ns: Long,
    val zramLifeP40Ns: Long,
    val zramLifeP50Ns: Long,
    val zramLifeP60Ns: Long,
    val zramLifeP70Ns: Long,
    val zramLifeP80Ns: Long,
    val zramLifeP90Ns: Long,
    val zramLifeP99Ns: Long,
    val zramLifeMaxNs: Long,
    val zramLifeEndWb: Long,
    val zramLifeEndReadback: Long,
    val zramLifeEndFree: Long,
    val ufsLifeTotal: Long,
    val ufsLifeSampled: Long,
    val ufsLifeRankN: Long,
    val ufsLifeAvgNs: Long,
    val ufsLifeP10Ns: Long,
    val ufsLifeP20Ns: Long,
    val ufsLifeP30Ns: Long,
    val ufsLifeP40Ns: Long,
    val ufsLifeP50Ns: Long,
    val ufsLifeP60Ns: Long,
    val ufsLifeP70Ns: Long,
    val ufsLifeP80Ns: Long,
    val ufsLifeP90Ns: Long,
    val ufsLifeP99Ns: Long,
    val ufsLifeMaxNs: Long,
    val ufsLifeEndReadback: Long,
    val ufsLifeEndFree: Long,
)

/**
 * 解析 /sys/block/zram0/hyperhold_report 中追加的统计段。
 *
 * 段以 "----- hyperhold io stat -----" 开头，之后每行形如 "key: value"。
 * 段之前还有 hyperhold 原有的 fault 记录（也含 "index:" 之类），所以必须先定位到标记行再解析。
 * 设备未刷入统计内核时整段不存在 —— 返回 null，不要抛异常。
 */
fun parseHyperholdReport(output: String): HyperholdStatResult? {
    val fields = mutableMapOf<String, Long>()
    var inSection = false

    output.lineSequence().forEach { line ->
        val t = line.trim()
        if (t.contains("hyperhold io stat")) {
            inSection = true
            return@forEach
        }
        if (!inSection) return@forEach
        val idx = t.indexOf(':')
        if (idx <= 0) return@forEach
        val key = t.substring(0, idx).trim()
        val value = t.substring(idx + 1).trim().toLongOrNull() ?: return@forEach
        fields[key] = value
    }

    if (fields.isEmpty()) return null
    fun v(k: String) = fields[k] ?: 0L

    return HyperholdStatResult(
        ioReqCnt = v("io_req_cnt"),
        ioReqBytes = v("io_req_bytes"),
        ufsReadReqCnt = v("hyperhold_in_times"),
        ufsWriteReqCnt = v("hyperhold_out_times"),
        ufsReadExtentCnt = v("read_extent_cnt"),
        ufsWriteExtentCnt = v("write_extent_cnt"),
        readInBytes = v("read_in_bytes"),
        writeRawBytes = v("write_raw_bytes"),
        writeUfsBytes = v("write_ufs_bytes"),
        faultoutFaultCnt = v("faultout_fault_cnt"),
        pfObjs = v("pf_objs"),
        pfHitObjs = v("pf_hit_objs"),
        pfNeverUsedObjs = v("pf_never_used_objs"),
        pfNeverUsedBytes = v("pf_never_used_bytes"),
        inflightPages = v("inflight_pages"),
        inflightPagesPeak = v("inflight_pages_peak"),
        movedInBytes = v("moved_in_bytes"),
        movedInPages = v("moved_in_pages"),
        cachePages = v("cache_pages"),
        cachePagesPeak = v("cache_pages_peak"),
        cacheMoveExts = v("cache_move_exts"),
        cacheMoveValidBytes = v("cache_move_valid_bytes"),
        cacheMoveValidBytesMin = v("cache_move_valid_bytes_min"),
        cacheMoveValidBytesMax = v("cache_move_valid_bytes_max"),
        cacheMoveValidBytesAvg = v("cache_move_valid_bytes_avg"),
        cacheMoveValidObjs = v("cache_move_valid_objs"),
        cacheMoveValidObjsMin = v("cache_move_valid_objs_min"),
        cacheMoveValidObjsMax = v("cache_move_valid_objs_max"),
        cacheMoveValidObjsAvgX100 = v("cache_move_valid_objs_avg_x100"),
        cacheMoveUtilAvgX100 = v("cache_move_util_avg_x100"),
        cacheMoveUtilMinX100 = v("cache_move_util_min_x100"),
        cacheMoveUtilMaxX100 = v("cache_move_util_max_x100"),
                
        pfDemandGroups = v("pf_demand_groups"),
        pfDemandObjs = v("pf_demand_objs"),
        pfDemandHitObjs = v("pf_demand_hit_objs"),
        pfDemandNeverObjs = v("pf_demand_never_objs"),
        pfDemandHitBytes = v("pf_demand_hit_bytes"),
        pfCachePages = v("pf_cache_pages"),
        pfCachePagesPeak = v("pf_cache_pages_peak"),
        zramLifeTotal = v("zram_life_total"),
        zramLifeSampled = v("zram_life_sampled"),
        zramLifeRankN = v("zram_life_rank_n"),
        zramLifeAvgNs = v("zram_life_avg_ns"),
        zramLifeP10Ns = v("zram_life_p10_ns"),
        zramLifeP20Ns = v("zram_life_p20_ns"),
        zramLifeP30Ns = v("zram_life_p30_ns"),
        zramLifeP40Ns = v("zram_life_p40_ns"),
        zramLifeP50Ns = v("zram_life_p50_ns"),
        zramLifeP60Ns = v("zram_life_p60_ns"),
        zramLifeP70Ns = v("zram_life_p70_ns"),
        zramLifeP80Ns = v("zram_life_p80_ns"),
        zramLifeP90Ns = v("zram_life_p90_ns"),
        zramLifeP99Ns = v("zram_life_p99_ns"),
        zramLifeMaxNs = v("zram_life_max_ns"),
        zramLifeEndWb = v("zram_life_end_wb"),
        zramLifeEndReadback = v("zram_life_end_readback"),
        zramLifeEndFree = v("zram_life_end_free"),
        ufsLifeTotal = v("ufs_life_total"),
        ufsLifeSampled = v("ufs_life_sampled"),
        ufsLifeRankN = v("ufs_life_rank_n"),
        ufsLifeAvgNs = v("ufs_life_avg_ns"),
        ufsLifeP10Ns = v("ufs_life_p10_ns"),
        ufsLifeP20Ns = v("ufs_life_p20_ns"),
        ufsLifeP30Ns = v("ufs_life_p30_ns"),
        ufsLifeP40Ns = v("ufs_life_p40_ns"),
        ufsLifeP50Ns = v("ufs_life_p50_ns"),
        ufsLifeP60Ns = v("ufs_life_p60_ns"),
        ufsLifeP70Ns = v("ufs_life_p70_ns"),
        ufsLifeP80Ns = v("ufs_life_p80_ns"),
        ufsLifeP90Ns = v("ufs_life_p90_ns"),
        ufsLifeP99Ns = v("ufs_life_p99_ns"),
        ufsLifeMaxNs = v("ufs_life_max_ns"),
        ufsLifeEndReadback = v("ufs_life_end_readback"),
        ufsLifeEndFree = v("ufs_life_end_free"),
    )
}

//新增 swap延迟统计
data class SwapinLatencyResult(
    val enabled: Long,
    val total: Long,
    val sampled: Long,
    val avgNs: Long,
    val p90Ns: Long,
    val p99Ns: Long,
    val maxNs: Long,
    val directReclaimTotal: Long,
    val directReclaimFgTotal: Long,
    val directReclaimSampled: Long,
    val directReclaimRankN: Long,
    val directReclaimAvgNs: Long,
    val directReclaimP10Ns: Long,
    val directReclaimP20Ns: Long,
    val directReclaimP30Ns: Long,
    val directReclaimP40Ns: Long,
    val directReclaimP50Ns: Long,
    val directReclaimP60Ns: Long,
    val directReclaimP70Ns: Long,
    val directReclaimP80Ns: Long,
    val directReclaimP90Ns: Long,
    val directReclaimP99Ns: Long,
    val directReclaimMaxNs: Long,
)

/**
 * 解析 /sys/kernel/mm/swapin_latency/stats（key: value 六行）。
 * 内核未打补丁时返回 null。
 */
fun parseSwapinLatencyStats(output: String): SwapinLatencyResult? {
    if (output.isBlank() || !output.contains("total_swapins"))
        return null

    val m = mutableMapOf<String, Long>()
    output.lineSequence().forEach { raw ->
        val t = raw.trim()
        val i = t.indexOf(':')
        if (i <= 0) return@forEach
        val v = t.substring(i + 1).trim().toLongOrNull() ?: return@forEach
        m[t.substring(0, i).trim()] = v
    }
    fun v(k: String) = m[k] ?: 0L

    return SwapinLatencyResult(
        enabled = 1,                       /* 能读到 stats 就算已注册；enable 状态单独读 */
        total = v("total_swapins"),
        sampled = v("sampled_swapins"),
        avgNs = v("avg_ns"),
        p90Ns = v("p90_ns"),
        p99Ns = v("p99_ns"),
        maxNs = v("max_ns"),
        directReclaimTotal = v("direct_reclaim_total"),
        directReclaimFgTotal = v("direct_reclaim_fg_total"),
        directReclaimSampled = v("direct_reclaim_sampled"),
        directReclaimRankN = v("direct_reclaim_rank_n"),
        directReclaimAvgNs = v("direct_reclaim_avg_ns"),
        directReclaimP10Ns = v("direct_reclaim_p10_ns"),
        directReclaimP20Ns = v("direct_reclaim_p20_ns"),
        directReclaimP30Ns = v("direct_reclaim_p30_ns"),
        directReclaimP40Ns = v("direct_reclaim_p40_ns"),
        directReclaimP50Ns = v("direct_reclaim_p50_ns"),
        directReclaimP60Ns = v("direct_reclaim_p60_ns"),
        directReclaimP70Ns = v("direct_reclaim_p70_ns"),
        directReclaimP80Ns = v("direct_reclaim_p80_ns"),
        directReclaimP90Ns = v("direct_reclaim_p90_ns"),
        directReclaimP99Ns = v("direct_reclaim_p99_ns"),
        directReclaimMaxNs = v("direct_reclaim_max_ns"),
    )
}
