package com.junj.metrics

import com.junj.device.adb.AdbExecutor
import com.junj.device.adb.ProcessAdbExecutor
import com.junj.domain.metrics.SamplingItem
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
    "echo $SAMPLE_MARKER $SECTION_SWAP_LAT",
    "cat /sys/kernel/mm/swapin_latency/stats",//新路径
    "echo \"swlat_enabled=$(cat /sys/kernel/mm/swapin_latency/enable 2>/dev/null)\"",
).joinToString("\n")

class MetricsCollector(
    private val adb: AdbExecutor = ProcessAdbExecutor,
) {
    fun collect(sampleStamp: Long): SamplingItem =
        parseSamplingItem(adb.rootShell(SAMPLE_SCRIPT).output, sampleStamp)
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

internal fun parseSamplingItem(rawOutput: String, sampleStamp: Long): SamplingItem {
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
        zramBdCount = (zramBd?.bdCount?.div(1024)) ?: 0,
        zramBdReads = (zramBd?.bdReads?.div(1024)) ?: 0,
        zramBdWrites = (zramBd?.bdWrites?.div(1024)) ?: 0,

        zswapStoredPages = labeledLong(zswap, "stored_pages"),
        zswapPoolTotalSize = labeledLong(zswap, "pool_total_size"),
        zswapPoolLimitHit = labeledLong(zswap, "pool_limit_hit"),
        zswapWrittenBackPages = labeledLong(zswap, "written_back_pages"),

        hhIoReqCnt = hyperhold?.ioReqCnt ?: 0,
        hhIoReqBytes = hyperhold?.ioReqBytes ?: 0,
        hhReadInBytes = hyperhold?.readInBytes ?: 0,
        hhWriteRawBytes = hyperhold?.writeRawBytes ?: 0,
        hhWriteUfsBytes = hyperhold?.writeUfsBytes ?: 0,
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

        hhPfDemandGroups = hyperhold?.pfDemandGroups ?: 0,
        hhPfDemandObjs = hyperhold?.pfDemandObjs ?: 0,
        hhPfDemandHitObjs = hyperhold?.pfDemandHitObjs ?: 0,
        hhPfDemandNeverObjs = hyperhold?.pfDemandNeverObjs ?: 0,
        hhPfDemandHitBytes = hyperhold?.pfDemandHitBytes ?: 0,
        hhPfCachePages = hyperhold?.pfCachePages ?: 0,
        hhPfCachePagesPeak = hyperhold?.pfCachePagesPeak ?: 0,

        swLatEnabled = swapinLatEnabled,
        swLatTotal = swapinLat?.total ?: 0,
        swLatSampled = swapinLat?.sampled ?: 0,
        swLatAvgNs = swapinLat?.avgNs ?: 0,
        swLatP90Ns = swapinLat?.p90Ns ?: 0,
        swLatP99Ns = swapinLat?.p99Ns ?: 0,
        swLatMaxNs = swapinLat?.maxNs ?: 0,
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
