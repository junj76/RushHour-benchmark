package com.junj.metrics

import com.junj.device.adb.AdbExecutor
import com.junj.device.adb.ProcessAdbExecutor
import com.junj.config.DEFAULT_EXTENT_SIZE_KB
import com.junj.domain.metrics.SamplingItem
import com.junj.domain.metrics.SwapinLatencyMetrics
import com.junj.domain.metrics.CacheMoveMetrics
import com.junj.metrics.parser.CommandType
import com.junj.metrics.parser.ResultField
import com.junj.metrics.parser.parseHyperholdReport
import com.junj.metrics.parser.parseSwapinLatencyStats
import com.junj.metrics.parser.parseVmstat
import com.junj.metrics.parser.parseZramBdStatResult
import com.junj.metrics.parser.parseZramMmStatResult
import com.junj.metrics.parser.regexFindField
import com.junj.output.logging.CommandDiagnostics

/** 分段标记行前缀：把一次 adb 调用的输出切成若干段。 */
internal const val SAMPLE_MARKER = "@@DSH@@"
internal const val SECTION_VMSTAT = "VMSTAT"
internal const val SECTION_MEMINFO = "MEMINFO"
internal const val SECTION_PRESSURE = "PRESSURE"
internal const val SECTION_THERMAL = "THERMAL"
internal const val SECTION_ZRAM_MM = "ZRAM_MM"
internal const val SECTION_ZRAM_BD = "ZRAM_BD"
internal const val SECTION_ZSWAP = "ZSWAP"
internal const val SECTION_HYPERHOLD = "HYPERHOLD"
internal const val SECTION_SWAP_LAT = "SWAP_LAT"

/**
 * 一整轮采样只发一次 adb 调用的脚本。
 *
 * runAdbRootShellCommand 是把脚本 pipe 给设备上的 `su -c sh`，sh 会从 stdin 读完整段脚本，
 * 所以多行命令只付一次 bash/adb.exe 进程启动与一次 ADB 往返的代价（原来是 10 次）。
 * 每段数据前打印一行 [SAMPLE_MARKER] 标记，取回后在宿主端切分，再交给原有解析器。
 *
 * 注意：脚本里不能出现会读取 stdin 的命令（例如无参数的 `cat`），否则会吃掉后面的脚本行。
 *
 * hyperhold 段是 Windows 分支新增的（上游统计内核在 /sys/block/zram0/hyperhold_report 里
 * 追加了 "hyperhold io stat" 段）；没有该节点的设备会在这里打印一行 cat 报错，
 * parseHyperholdReport 返回 null，再由 CommandDiagnostics 留档，不影响其它段。
 */
internal val SAMPLE_SCRIPT: String = listOf(
    "echo $SAMPLE_MARKER $SECTION_VMSTAT",
    "vmstat 1 2",
    "echo $SAMPLE_MARKER $SECTION_MEMINFO",
    "cat /proc/meminfo",
    "echo $SAMPLE_MARKER $SECTION_PRESSURE",
    "cat /proc/pressure/memory",
    "echo $SAMPLE_MARKER $SECTION_THERMAL",
    "dumpsys thermalservice",
    "echo $SAMPLE_MARKER $SECTION_ZRAM_MM",
    "cat /sys/block/zram0/mm_stat",
    "echo $SAMPLE_MARKER $SECTION_ZRAM_BD",
    "cat /sys/block/zram0/bd_stat",
    "echo $SAMPLE_MARKER $SECTION_ZSWAP",
    "echo \"stored_pages=\$(cat /sys/kernel/debug/zswap/stored_pages 2>/dev/null)\"",
    "echo \"pool_total_size=\$(cat /sys/kernel/debug/zswap/pool_total_size 2>/dev/null)\"",
    "echo \"pool_limit_hit=\$(cat /sys/kernel/debug/zswap/pool_limit_hit 2>/dev/null)\"",
    "echo \"written_back_pages=\$(cat /sys/kernel/debug/zswap/written_back_pages 2>/dev/null)\"",
    "echo $SAMPLE_MARKER $SECTION_HYPERHOLD",
    "cat /sys/block/zram0/hyperhold_report",
    "grep -E '^hyperhold_(in|out)_times:' /dev/memcg/memory.psi_health_info 2>/dev/null",
    "echo $SAMPLE_MARKER $SECTION_SWAP_LAT",
    "cat /sys/kernel/mm/swapin_latency/stats",//新路径
    "echo \"swlat_enabled=$(cat /sys/kernel/mm/swapin_latency/enable 2>/dev/null)\"",
).joinToString("\n")

class MetricsCollector(
    private val adb: AdbExecutor = ProcessAdbExecutor,
    private val extentSizeKb: Int = DEFAULT_EXTENT_SIZE_KB,
) {
    fun collect(sampleStamp: Long): SamplingItem =
        parseSamplingItem(
            adb.rootShell(SAMPLE_SCRIPT).output,
            sampleStamp,
            extentSizeKb,
        )
}

/** 按标记行把整段输出切成 段名 -> 段内容；每段内容与原来单独执行该命令得到的输出一致。 */
internal fun splitSampleSections(rawOutput: String): Map<String, String> {
    val sections = LinkedHashMap<String, String>()
    val buffer = StringBuilder()
    var current: String? = null

    rawOutput.lineSequence().forEach { line ->
        val trimmed = line.trim()
        if (trimmed.startsWith(SAMPLE_MARKER)) {
            current?.let { sections[it] = buffer.toString() }
            buffer.setLength(0)
            current = trimmed.removePrefix(SAMPLE_MARKER).trim()
        } else if (current != null) {
            buffer.append(line).append('\n')
        }
    }
    current?.let { sections[it] = buffer.toString() }

    return sections
}

internal fun parseSamplingItem(
    rawOutput: String,
    sampleStamp: Long,
    extentSizeKb: Int = DEFAULT_EXTENT_SIZE_KB,
): SamplingItem {
    val sections = splitSampleSections(rawOutput)

    val vmstatSection = sections[SECTION_VMSTAT].orEmpty()
    val vmstat = parseVmstat(vmstatSection)
    if (vmstat == null) {
        // vmstat 跑成功了但解析不出数字：多半是这台机器的 vmstat 列数/表头和解析规则不一致。
        CommandDiagnostics.record("vmstat/unparsed", "vmstat", vmstatSection)
    }

    val memInfo = sections[SECTION_MEMINFO].orEmpty()
    val pressureMemory = sections[SECTION_PRESSURE].orEmpty()
    val thermal = sections[SECTION_THERMAL].orEmpty()
    if (regexFindField(CommandType.DUMPSYS_THERMALSERVICE, ResultField.BIG_TEMP, thermal) == null) {
        // 温度一项都解析不到：多半是这台 ROM 的 dumpsys 输出格式（或温区名字）不一样。
        CommandDiagnostics.record(
            "thermalservice/no-temps",
            "dumpsys thermalservice",
            keepFromHalSection(thermal),
        )
    }

    val zramMmSection = sections[SECTION_ZRAM_MM].orEmpty()
    val zramMm = parseZramMmStatResult(zramMmSection)
    if (zramMm == null) {
        CommandDiagnostics.record("zram-mm_stat/unparsed", "cat /sys/block/zram0/mm_stat", zramMmSection)
    }

    val zramBd = parseZramBdStatResult(sections[SECTION_ZRAM_BD].orEmpty())
    val zswap = sections[SECTION_ZSWAP].orEmpty()

    val hyperholdSection = sections[SECTION_HYPERHOLD].orEmpty()
    val hyperhold = parseHyperholdReport(hyperholdSection)
    if (hyperhold == null) {
        CommandDiagnostics.record(
            "hyperhold/unparsed",
            "cat /sys/block/zram0/hyperhold_report",
            hyperholdSection,
        )
    }
    //从分段里取（复用你已有的 labeledLong()）
    val swapLatSection = sections[SECTION_SWAP_LAT].orEmpty()
    val swapinLat = parseSwapinLatencyStats(swapLatSection)
    val swapinLatEnabled = labeledLong(swapLatSection, "swlat_enabled")

    val readInBytes = hyperhold?.readInBytes ?: 0
    val writeUfsBytes = hyperhold?.writeUfsBytes ?: 0
    val extentBytes = extentSizeKb.coerceAtLeast(1) * 1024L
    val readExtentCnt = hyperhold?.ufsReadExtentCnt?.takeIf { it > 0 }
        ?: if (readInBytes > 0) readInBytes / extentBytes else 0
    val writeExtentCnt = hyperhold?.ufsWriteExtentCnt?.takeIf { it > 0 }
        ?: if (writeUfsBytes > 0) writeUfsBytes / extentBytes else 0

    return SamplingItem(
        sampleStamp = sampleStamp,

        meminfoMemTotal = regexFindField(CommandType.CAT_PROC_MEMINFO, ResultField.MEM_TOTAL, memInfo)?.toLongOrNull() ?: 0,
        meminfoMemFree = regexFindField(CommandType.CAT_PROC_MEMINFO, ResultField.MEM_FREE, memInfo)?.toLongOrNull() ?: 0,
        meminfoMemAvailable = regexFindField(CommandType.CAT_PROC_MEMINFO, ResultField.MEM_AVAILABLE, memInfo)?.toLongOrNull() ?: 0,
        meminfoSwapTotal = regexFindField(CommandType.CAT_PROC_MEMINFO, ResultField.SWAP_TOTAL, memInfo)?.toLongOrNull() ?: 0,
        meminfoSwapFree = regexFindField(CommandType.CAT_PROC_MEMINFO, ResultField.SWAP_FREE, memInfo)?.toLongOrNull() ?: 0,
        meminfoSwapCached = regexFindField(CommandType.CAT_PROC_MEMINFO, ResultField.SWAP_CACHED, memInfo)?.toLongOrNull() ?: 0,

        psiSome = regexFindField(CommandType.CAT_PROC_PRESSURE_MEMORY, ResultField.PSI_SOME_TOTAL, pressureMemory)?.toLongOrNull() ?: 0,
        psiFull = regexFindField(CommandType.CAT_PROC_PRESSURE_MEMORY, ResultField.PSI_FULL_TOTAL, pressureMemory)?.toLongOrNull() ?: 0,

        vmstatR = vmstat?.vmstatR ?: 0,
        vmstatB = vmstat?.vmstatB ?: 0,
        vmstatSwpd = vmstat?.vmstatSwpd ?: 0L,
        vmstatFree = vmstat?.vmstatFree ?: 0L,
        vmstatBuff = vmstat?.vmstatBuff ?: 0L,
        vmstatCache = vmstat?.vmstatCache ?: 0L,
        vmstatSi = vmstat?.vmstatSi ?: 0L,
        vmstatSo = vmstat?.vmstatSo ?: 0L,
        vmstatBi = vmstat?.vmstatBi ?: 0L,
        vmstatBo = vmstat?.vmstatBo ?: 0L,
        vmstatIn = vmstat?.vmstatIn ?: 0L,
        vmstatCs = vmstat?.vmstatCs ?: 0L,
        vmstatUs = vmstat?.vmstatUs ?: 0,
        vmstatSy = vmstat?.vmstatSy ?: 0,
        vmstatId = vmstat?.vmstatId ?: 0,
        vmstatWa = vmstat?.vmstatWa ?: 0,

        bigTemp = regexFindField(CommandType.DUMPSYS_THERMALSERVICE, ResultField.BIG_TEMP, thermal)?.toDoubleOrNull() ?: 0.0,
        midTemp = regexFindField(CommandType.DUMPSYS_THERMALSERVICE, ResultField.MID_TEMP, thermal)?.toDoubleOrNull() ?: 0.0,
        littleTemp = regexFindField(CommandType.DUMPSYS_THERMALSERVICE, ResultField.LITTLE_TEMP, thermal)?.toDoubleOrNull() ?: 0.0,
        socThermTemp = regexFindField(CommandType.DUMPSYS_THERMALSERVICE, ResultField.SOC_THERM_TEMP, thermal)?.toDoubleOrNull() ?: 0.0,
        virtualSkinTemp = regexFindField(CommandType.DUMPSYS_THERMALSERVICE, ResultField.VIRTUAL_SKIN_TEMP, thermal)?.toDoubleOrNull() ?: 0.0,

        zramOrigDataSize = (zramMm?.origDataSize?.div(1024)) ?: 0,
        zramComprDataSize = (zramMm?.comprDataSize?.div(1024)) ?: 0,
        zramMemUsedTotal = (zramMm?.memUsedTotal?.div(1024)) ?: 0,
        zramMemUsedMax = (zramMm?.memUsedMax?.div(1024)) ?: 0,
        // TODO(stats): bd_stat 输出的是 4KB 块数，不是字节。这里除以 1024
        // 会让后续带宽约小 1024 倍并丢失低位精度；后续应保存原始块数并同步修正 CsvWriter。
        zramBdCount = (zramBd?.bdCount?.div(1024)) ?: 0,
        zramBdReads = (zramBd?.bdReads?.div(1024)) ?: 0,
        zramBdWrites = (zramBd?.bdWrites?.div(1024)) ?: 0,

        zswapStoredPages = labeledLong(zswap, "stored_pages"),
        zswapPoolTotalSize = labeledLong(zswap, "pool_total_size"),
        zswapPoolLimitHit = labeledLong(zswap, "pool_limit_hit"),
        zswapWrittenBackPages = labeledLong(zswap, "written_back_pages"),

        hhIoReqCnt = hyperhold?.ioReqCnt ?: 0,
        hhIoReqBytes = hyperhold?.ioReqBytes ?: 0,
        hhUfsReadReqCnt = readExtentCnt,
        hhUfsWriteReqCnt = writeExtentCnt,
        hhUfsReadBatchCnt = hyperhold?.ufsReadReqCnt ?: 0,
        hhUfsWriteBatchCnt = hyperhold?.ufsWriteReqCnt ?: 0,
        hhUfsReadExtentCnt = readExtentCnt,
        hhUfsWriteExtentCnt = writeExtentCnt,
        hhReadInBytes = readInBytes,
        hhWriteRawBytes = hyperhold?.writeRawBytes ?: 0,
        hhWriteUfsBytes = writeUfsBytes,
        hhFaultoutFaultCnt = hyperhold?.faultoutFaultCnt ?: 0,
        hhPfObjs = hyperhold?.pfObjs ?: 0,
        hhPfHitObjs = hyperhold?.pfHitObjs ?: 0,
        hhPfNeverUsedObjs = hyperhold?.pfNeverUsedObjs ?: 0,
        hhPfNeverUsedBytes = hyperhold?.pfNeverUsedBytes ?: 0,
        hhInflightPages = hyperhold?.inflightPages ?: 0,
        hhInflightPagesPeak = hyperhold?.inflightPagesPeak ?: 0,
        hhMovedInBytes = hyperhold?.movedInBytes ?: 0,
        hhMovedInPages = hyperhold?.movedInPages ?: 0,
        hhCachePages = hyperhold?.cachePages ?: 0,
        hhCachePagesPeak = hyperhold?.cachePagesPeak ?: 0,
        cacheMove = CacheMoveMetrics(
            extents = hyperhold?.cacheMoveExts ?: 0,
            validBytes = hyperhold?.cacheMoveValidBytes ?: 0,
            validBytesMin = hyperhold?.cacheMoveValidBytesMin ?: 0,
            validBytesMax = hyperhold?.cacheMoveValidBytesMax ?: 0,
            validBytesAvg = hyperhold?.cacheMoveValidBytesAvg ?: 0,
            validObjs = hyperhold?.cacheMoveValidObjs ?: 0,
            validObjsMin = hyperhold?.cacheMoveValidObjsMin ?: 0,
            validObjsMax = hyperhold?.cacheMoveValidObjsMax ?: 0,
            validObjsAvgX100 = hyperhold?.cacheMoveValidObjsAvgX100 ?: 0,
            utilAvgX100 = hyperhold?.cacheMoveUtilAvgX100 ?: 0,
            utilMinX100 = hyperhold?.cacheMoveUtilMinX100 ?: 0,
            utilMaxX100 = hyperhold?.cacheMoveUtilMaxX100 ?: 0,
        ),

        hhPfDemandGroups = hyperhold?.pfDemandGroups ?: 0,
        hhPfDemandObjs = hyperhold?.pfDemandObjs ?: 0,
        hhPfDemandHitObjs = hyperhold?.pfDemandHitObjs ?: 0,
        hhPfDemandNeverObjs = hyperhold?.pfDemandNeverObjs ?: 0,
        hhPfDemandHitBytes = hyperhold?.pfDemandHitBytes ?: 0,
        hhPfCachePages = hyperhold?.pfCachePages ?: 0,
        hhPfCachePagesPeak = hyperhold?.pfCachePagesPeak ?: 0,
        hhZramLifeTotal = hyperhold?.zramLifeTotal ?: 0,
        hhZramLifeSampled = hyperhold?.zramLifeSampled ?: 0,
        hhZramLifeRankN = hyperhold?.zramLifeRankN ?: 0,
        hhZramLifeAvgNs = hyperhold?.zramLifeAvgNs ?: 0,
        hhZramLifeP10Ns = hyperhold?.zramLifeP10Ns ?: 0,
        hhZramLifeP20Ns = hyperhold?.zramLifeP20Ns ?: 0,
        hhZramLifeP30Ns = hyperhold?.zramLifeP30Ns ?: 0,
        hhZramLifeP40Ns = hyperhold?.zramLifeP40Ns ?: 0,
        hhZramLifeP50Ns = hyperhold?.zramLifeP50Ns ?: 0,
        hhZramLifeP60Ns = hyperhold?.zramLifeP60Ns ?: 0,
        hhZramLifeP70Ns = hyperhold?.zramLifeP70Ns ?: 0,
        hhZramLifeP80Ns = hyperhold?.zramLifeP80Ns ?: 0,
        hhZramLifeP90Ns = hyperhold?.zramLifeP90Ns ?: 0,
        hhZramLifeP99Ns = hyperhold?.zramLifeP99Ns ?: 0,
        hhZramLifeMaxNs = hyperhold?.zramLifeMaxNs ?: 0,
        hhZramLifeEndWb = hyperhold?.zramLifeEndWb ?: 0,
        hhZramLifeEndReadback = hyperhold?.zramLifeEndReadback ?: 0,
        hhZramLifeEndFree = hyperhold?.zramLifeEndFree ?: 0,
        hhUfsLifeTotal = hyperhold?.ufsLifeTotal ?: 0,
        hhUfsLifeSampled = hyperhold?.ufsLifeSampled ?: 0,
        hhUfsLifeRankN = hyperhold?.ufsLifeRankN ?: 0,
        hhUfsLifeAvgNs = hyperhold?.ufsLifeAvgNs ?: 0,
        hhUfsLifeP10Ns = hyperhold?.ufsLifeP10Ns ?: 0,
        hhUfsLifeP20Ns = hyperhold?.ufsLifeP20Ns ?: 0,
        hhUfsLifeP30Ns = hyperhold?.ufsLifeP30Ns ?: 0,
        hhUfsLifeP40Ns = hyperhold?.ufsLifeP40Ns ?: 0,
        hhUfsLifeP50Ns = hyperhold?.ufsLifeP50Ns ?: 0,
        hhUfsLifeP60Ns = hyperhold?.ufsLifeP60Ns ?: 0,
        hhUfsLifeP70Ns = hyperhold?.ufsLifeP70Ns ?: 0,
        hhUfsLifeP80Ns = hyperhold?.ufsLifeP80Ns ?: 0,
        hhUfsLifeP90Ns = hyperhold?.ufsLifeP90Ns ?: 0,
        hhUfsLifeP99Ns = hyperhold?.ufsLifeP99Ns ?: 0,
        hhUfsLifeMaxNs = hyperhold?.ufsLifeMaxNs ?: 0,
        hhUfsLifeEndReadback = hyperhold?.ufsLifeEndReadback ?: 0,
        hhUfsLifeEndFree = hyperhold?.ufsLifeEndFree ?: 0,

        swLatency = SwapinLatencyMetrics(
            enabled = swapinLatEnabled,
            total = swapinLat?.total ?: 0,
            sampled = swapinLat?.sampled ?: 0,
            avgNs = swapinLat?.avgNs ?: 0,
            p90Ns = swapinLat?.p90Ns ?: 0,
            p99Ns = swapinLat?.p99Ns ?: 0,
            maxNs = swapinLat?.maxNs ?: 0,
        ),
        directReclaimTotal = swapinLat?.directReclaimTotal ?: 0,
        directReclaimFgTotal = swapinLat?.directReclaimFgTotal ?: 0,
        directReclaimSampled = swapinLat?.directReclaimSampled ?: 0,
        directReclaimRankN = swapinLat?.directReclaimRankN ?: 0,
        directReclaimAvgNs = swapinLat?.directReclaimAvgNs ?: 0,
        directReclaimP10Ns = swapinLat?.directReclaimP10Ns ?: 0,
        directReclaimP20Ns = swapinLat?.directReclaimP20Ns ?: 0,
        directReclaimP30Ns = swapinLat?.directReclaimP30Ns ?: 0,
        directReclaimP40Ns = swapinLat?.directReclaimP40Ns ?: 0,
        directReclaimP50Ns = swapinLat?.directReclaimP50Ns ?: 0,
        directReclaimP60Ns = swapinLat?.directReclaimP60Ns ?: 0,
        directReclaimP70Ns = swapinLat?.directReclaimP70Ns ?: 0,
        directReclaimP80Ns = swapinLat?.directReclaimP80Ns ?: 0,
        directReclaimP90Ns = swapinLat?.directReclaimP90Ns ?: 0,
        directReclaimP99Ns = swapinLat?.directReclaimP99Ns ?: 0,
        directReclaimMaxNs = swapinLat?.directReclaimMaxNs ?: 0,
    )
}

/** 记录 thermalservice 原始输出时，从 "Current temperatures" 这段开始截，免得前面无关内容把温度段挤出记录范围。 */
private fun keepFromHalSection(output: String): String {
    val index = output.indexOf("Current temperatures")
    return if (index >= 0) output.substring(index) else output
}

/** 解析 `key=value` 形式的段内容；文件不存在时 value 为空，回退为 0。 */
private fun labeledLong(section: String, key: String): Long =
    section.lineSequence()
        .firstOrNull { it.trim().startsWith("$key=") }
        ?.substringAfter('=')
        ?.trim()
        ?.toLongOrNull()
        ?: 0L
