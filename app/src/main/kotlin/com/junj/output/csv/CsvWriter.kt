package com.junj.output.csv

import com.junj.config.DEFAULT_EXTENT_SIZE_KB
import com.junj.domain.metrics.flashKbDelta

import com.junj.domain.ExperimentResults
import com.junj.domain.launch.LaunchApplicationItem
import com.junj.domain.metrics.SamplingItem
import com.junj.domain.survival.AppSurvivalResult
import com.junj.output.ExperimentOutputPaths
import java.io.File

fun saveCsv(
    results: ExperimentResults,
    output: ExperimentOutputPaths,
    sampleIntervalMs: Long,
    extentSizeKb: Int = DEFAULT_EXTENT_SIZE_KB,
) {
    saveLaunchResultsToCsv(
        results.launches,
        output.launchCsv,
    )
    saveSampleResultsToCsv(
        results.samples,
        output.sampleCsv,
        sampleIntervalMs,
        extentSizeKb,
    )
    saveSurvivalResultsToCsv(
        results.survivals,
        output.survivalCsv,
    )
}

fun saveSurvivalResultsToCsv(
    results: List<AppSurvivalResult>,
    outputFile: File,
) {
    outputFile.parentFile?.mkdirs()

    outputFile.bufferedWriter(Charsets.UTF_8).use { writer ->
        writer.appendLine(
            listOf(
                "round",
                "launchPosition",
                "appName",
                "packageName",
                "launchedPid",
                "pidAtRoundEnd",
                "originalProcessAlive",
                "appCurrentlyRunning",
            ).joinToString(",")
        )

        results.forEach { item ->
            writer.appendLine(
                listOf(
                    item.round,
                    item.launchPosition,
                    item.appName,
                    item.packageName,
                    item.launchedPid ?: "",
                    item.pidAtRoundEnd ?: "",
                    item.originalProcessAlive,
                    item.appCurrentlyRunning,
                ).joinToString(",") { value ->
                    escapeCsv(value.toString())
                }
            )
        }
    }
}

fun saveLaunchResultsToCsv(results: List<LaunchApplicationItem>, outputFile: File, ) {
    outputFile.parentFile?.mkdirs()

    outputFile.bufferedWriter(Charsets.UTF_8).use { writer ->
        writer.appendLine(
            listOf(
                "launchStamp(ms)",
                "amStartRound",
                "amStartAppName",
                "amStartLaunchState",
                "amStartTotalTime(ms)",
                "amStartWaitTime(ms)",
                "amStartStatus",
                "jankyFrames(%)",
                "p50RenderLat(ms)",
                "p90RenderLat(ms)",
                "p95RenderLat(ms)",
                "p99RenderLat(ms)",
                "totalPss(KB)",
            ).joinToString(",")
        )

        results.forEach { item ->
            writer.appendLine(
                listOf(
                    item.launchStamp,
                    item.amStartRound,
                    item.amStartAppName,
                    item.amStartLaunchState,
                    item.amStartTotalTime,
                    item.amStartWaitTime,
                    item.amStartStatus,
                    item.dumpsysGfxInfoJankyFrames,
                    item.dumpsysGfxInfoP50RenderLat,
                    item.dumpsysGfxInfoP90RenderLat,
                    item.dumpsysGfxInfoP95RenderLat,
                    item.dumpsysGfxInfoP99RenderLat,
                    item.dumpsysMemInfoTotalPss,
                ).joinToString(",") { value ->
                    escapeCsv(value.toString())
                }
            )
        }
    }
}

fun escapeCsv(value: String): String {
    val escaped = value.replace("\"", "\"\"")
    return if (
        value.contains(',') ||
        value.contains('"') ||
        value.contains('\n') ||
        value.contains('\r')
    ) {
        "\"$escaped\""
    } else {
        escaped
    }
}

fun saveSampleResultsToCsv(
    results: List<SamplingItem>,
    outputFile: File,
    sampleIntervalMs: Long,
    extentSizeKb: Int = DEFAULT_EXTENT_SIZE_KB,
) {
    require(sampleIntervalMs > 0) { "sampleIntervalMs must be positive" }
    outputFile.parentFile?.mkdirs()

    outputFile.bufferedWriter(Charsets.UTF_8).use { writer ->
        writer.appendLine(
            listOf(
                "sampleStamp(ms)",
                "memTotal(KB)",
                "memFree(KB)",
                "memAvailable(KB)",
                "swapTotal(KB)",
                "swapFree(KB)",
                "swapCached(KB)",
                "psiSome(us)",
                "psiFull(us)",
                "vmstatR/runnableProcesses",
                "vmstatB/blockedProcesses",
                "vmstatSwpd/swapUsed(KB)",
                "vmstatFree/freeMemory(KB)",
                "vmstatBuff/bufferMemory(KB)",
                "vmstatCache/cacheMemory(KB)",
                "vmstatSi/swapInBw(KB/s)",
                "vmstatSo/swapOutBw(KB/s)",
                "vmstatBi/blockInput(blocks/s)",
                "vmstatBo/blockOutput(blocks/s)",
                "vmstatIn/Interrupts(time/s)",
                "vmstatCs/contextSwitches(time/s)",
                "vmstatUs/userCpuTime(%)",
                "vmstatSy/kernelCpuTime(%)",
                "vmstatId/idleCpuTime(%)",
                "vmstatWa/waitIoCpuTime(%)",
                "bigTemp(°C)",
                "midTemp(°C)",
                "littleTemp(°C)",
                "socThermTemp(°C)",
                "virtualSkinTemp(°C)",
                "zramOrigDataSize(KB)",
                "zramComprDataSize(KB)",
                "zramMemUsedTotal(KB)",
                "zramMemUsedMax(KB)",
                "zramBdCount(KB)",
                "zramBdReads(KB)",
                "zramBdWrites(KB)",
                "zramBdReadBw(MB/s)",
                "zramBdWriteBw(MB/s)",
                "zswapStoredPages",
                "zswapStoredSize(KB)",
                "zswapPoolTotalSize(KB)",
                "zswapPoolLimitHit",
                "zswapWrittenBackPages",
                "zswapWrittenBackSize(KB)",
                "zswapWriteBw(MB/s)",
                "flashDeviceRead(KB/interval)",
                "flashDeviceWrite(KB/interval)",
                "extentSizeKb",
                "hhIoReqCnt",
                "hhIoReqBytes",
                "hhUfsReadReqCnt",
                "hhUfsWriteReqCnt",
                "hhUfsReadBatchCnt",
                "hhUfsWriteBatchCnt",
                "hhUfsReadExtentCnt",
                "hhUfsWriteExtentCnt",
                "hhReadInBytes",
                "hhReadAmpX100",
                "hhWriteRawBytes",
                "hhWriteUfsBytes",
                "hhWriteAmpX100",
                "hhFaultoutFaultCnt",
                "hhPfObjs",
                "hhPfHitObjs",
                "hhPfNeverUsedObjs",
                "hhPfNeverUsedBytes",
                "hhPfHitRateX100",
                "hhPfDemandGroups",
                "hhPfDemandObjs",
                "hhPfDemandHitObjs",
                "hhPfDemandNeverObjs",
                "hhPfDemandHitBytes",
                "hhPfDemandHitRateX100",
                "hhPfCachePages",
                "hhPfCachePagesPeak",
                "hhZramLifeTotal",
                "hhZramLifeSampled",
                "hhZramLifeRankN",
                "hhZramLifeAvgNs",
                "hhZramLifeP10Ns",
                "hhZramLifeP20Ns",
                "hhZramLifeP30Ns",
                "hhZramLifeP40Ns",
                "hhZramLifeP50Ns",
                "hhZramLifeP60Ns",
                "hhZramLifeP70Ns",
                "hhZramLifeP80Ns",
                "hhZramLifeP90Ns",
                "hhZramLifeP99Ns",
                "hhZramLifeMaxNs",
                "hhZramLifeEndWb",
                "hhZramLifeEndReadback",
                "hhZramLifeEndFree",
                "hhUfsLifeTotal",
                "hhUfsLifeSampled",
                "hhUfsLifeRankN",
                "hhUfsLifeAvgNs",
                "hhUfsLifeP10Ns",
                "hhUfsLifeP20Ns",
                "hhUfsLifeP30Ns",
                "hhUfsLifeP40Ns",
                "hhUfsLifeP50Ns",
                "hhUfsLifeP60Ns",
                "hhUfsLifeP70Ns",
                "hhUfsLifeP80Ns",
                "hhUfsLifeP90Ns",
                "hhUfsLifeP99Ns",
                "hhUfsLifeMaxNs",
                "hhUfsLifeEndReadback",
                "hhUfsLifeEndFree",
                "hhInflightPages",
                "hhInflightPagesPeak",
                "hhMovedInBytes",
                "hhMovedInPages",
                "hhCachePages",
                "hhCachePagesPeak",
                "hhCacheMoveExts",
                "hhCacheMoveValidBytes",
                "hhCacheMoveValidBytesMin",
                "hhCacheMoveValidBytesMax",
                "hhCacheMoveValidBytesAvg",
                "hhCacheMoveValidObjs",
                "hhCacheMoveValidObjsMin",
                "hhCacheMoveValidObjsMax",
                "hhCacheMoveValidObjsAvgX100",
                "hhCacheMoveUtilAvgX100",
                "hhCacheMoveUtilMinX100",
                "hhCacheMoveUtilMaxX100",
                "swLatEnabled",
                "swLatTotal",
                "swLatSampled",
                "swLatAvgNs",
                "swLatP90Ns",
                "swLatP99Ns",
                "swLatMaxNs",
                "directReclaimTotal",
                "directReclaimFgTotal",
                "directReclaimSampled",
                "directReclaimRankN",
                "directReclaimAvgNs",
                "directReclaimP10Ns",
                "directReclaimP20Ns",
                "directReclaimP30Ns",
                "directReclaimP40Ns",
                "directReclaimP50Ns",
                "directReclaimP60Ns",
                "directReclaimP70Ns",
                "directReclaimP80Ns",
                "directReclaimP90Ns",
                "directReclaimP99Ns",
                "directReclaimMaxNs",
                "hhReadBw(MB/s)",
                "hhWriteBw(MB/s)",
            ).joinToString(",")
        )

        results.forEachIndexed { index, item ->
            val previous = results.getOrNull(index - 1)
            val elapsedMs = previous?.let { item.sampleStamp - it.sampleStamp } ?: 0L
            writer.appendLine(
                listOf(
                    item.sampleStamp,
                    item.meminfoMemTotal,
                    item.meminfoMemFree,
                    item.meminfoMemAvailable,
                    item.meminfoSwapTotal,
                    item.meminfoSwapFree,
                    item.meminfoSwapCached,
                    item.psiSome,
                    item.psiFull,
                    item.vmstatR,
                    item.vmstatB,
                    item.vmstatSwpd,
                    item.vmstatFree,
                    item.vmstatBuff,
                    item.vmstatCache,
                    item.vmstatSi,
                    item.vmstatSo,
                    item.vmstatBi,
                    item.vmstatBo,
                    item.vmstatIn,
                    item.vmstatCs,
                    item.vmstatUs,
                    item.vmstatSy,
                    item.vmstatId,
                    item.vmstatWa,
                    item.bigTemp,
                    item.midTemp,
                    item.littleTemp,
                    item.socThermTemp,
                    item.virtualSkinTemp,
                    item.zramOrigDataSize,
                    item.zramComprDataSize,
                    item.zramMemUsedTotal,
                    item.zramMemUsedMax,
                    item.zramBdCount,
                    item.zramBdReads,
                    item.zramBdWrites,
                    counterRateMbPerSecond(item.zramBdReads, previous?.zramBdReads, elapsedMs, 1L),
                    counterRateMbPerSecond(item.zramBdWrites, previous?.zramBdWrites, elapsedMs, 1L),
                    item.zswapStoredPages,
                    item.zswapStoredSizeKb,
                    item.zswapPoolTotalSize,
                    item.zswapPoolLimitHit,
                    item.zswapWrittenBackPages,
                    item.zswapWrittenBackSizeKb,
                    // 池满拒绝计数不能算进写回吞吐。首样本无运行前基线，速率记 0。
                    if (previous != null && item.pageSizeKb == previous.pageSizeKb) {
                        counterRateMbPerSecond(item.zswapWrittenBackPages, previous.zswapWrittenBackPages, elapsedMs, item.pageSizeKb)
                    } else 0.0,
                    flashKbDelta(item.flashDeviceReadKb, previous?.flashDeviceReadKb),
                    flashKbDelta(item.flashDeviceWriteKb, previous?.flashDeviceWriteKb),
                    extentSizeKb,
                    item.hhIoReqCnt,
                    item.hhIoReqBytes,
                    item.hhUfsReadReqCnt,
                    item.hhUfsWriteReqCnt,
                    item.hhUfsReadBatchCnt,
                    item.hhUfsWriteBatchCnt,
                    item.hhUfsReadExtentCnt,
                    item.hhUfsWriteExtentCnt,
                    item.hhReadInBytes,
                    if (item.hhIoReqBytes > 0) item.hhReadInBytes * 100 / item.hhIoReqBytes else 0,
                    item.hhWriteRawBytes,
                    item.hhWriteUfsBytes,
                    if (item.hhWriteRawBytes > 0) item.hhWriteUfsBytes * 100 / item.hhWriteRawBytes else 0,
                    item.hhFaultoutFaultCnt,
                    item.hhPfObjs,
                    item.hhPfHitObjs,
                    item.hhPfNeverUsedObjs,
                    item.hhPfNeverUsedBytes,
                    if (item.hhPfHitObjs + item.hhPfNeverUsedObjs > 0) item.hhPfHitObjs * 100 / (item.hhPfHitObjs + item.hhPfNeverUsedObjs) else 0,
                    item.hhPfDemandGroups,
                    item.hhPfDemandObjs,
                    item.hhPfDemandHitObjs,
                    item.hhPfDemandNeverObjs,
                    item.hhPfDemandHitBytes,
                    if (item.hhPfObjs > 0) item.hhPfHitObjs * 100 / item.hhPfObjs else 0,
                    item.hhPfCachePages,
                    item.hhPfCachePagesPeak,
                    item.hhZramLifeTotal,
                    item.hhZramLifeSampled,
                    item.hhZramLifeRankN,
                    item.hhZramLifeAvgNs,
                    item.hhZramLifeP10Ns,
                    item.hhZramLifeP20Ns,
                    item.hhZramLifeP30Ns,
                    item.hhZramLifeP40Ns,
                    item.hhZramLifeP50Ns,
                    item.hhZramLifeP60Ns,
                    item.hhZramLifeP70Ns,
                    item.hhZramLifeP80Ns,
                    item.hhZramLifeP90Ns,
                    item.hhZramLifeP99Ns,
                    item.hhZramLifeMaxNs,
                    item.hhZramLifeEndWb,
                    item.hhZramLifeEndReadback,
                    item.hhZramLifeEndFree,
                    item.hhUfsLifeTotal,
                    item.hhUfsLifeSampled,
                    item.hhUfsLifeRankN,
                    item.hhUfsLifeAvgNs,
                    item.hhUfsLifeP10Ns,
                    item.hhUfsLifeP20Ns,
                    item.hhUfsLifeP30Ns,
                    item.hhUfsLifeP40Ns,
                    item.hhUfsLifeP50Ns,
                    item.hhUfsLifeP60Ns,
                    item.hhUfsLifeP70Ns,
                    item.hhUfsLifeP80Ns,
                    item.hhUfsLifeP90Ns,
                    item.hhUfsLifeP99Ns,
                    item.hhUfsLifeMaxNs,
                    item.hhUfsLifeEndReadback,
                    item.hhUfsLifeEndFree,
                    item.hhInflightPages,
                    item.hhInflightPagesPeak,
                    item.hhMovedInBytes,
                    item.hhMovedInPages,
                    item.hhCachePages,
                    item.hhCachePagesPeak,
                    item.cacheMove.extents,
                    item.cacheMove.validBytes,
                    item.cacheMove.validBytesMin,
                    item.cacheMove.validBytesMax,
                    item.cacheMove.validBytesAvg,
                    item.cacheMove.validObjs,
                    item.cacheMove.validObjsMin,
                    item.cacheMove.validObjsMax,
                    item.cacheMove.validObjsAvgX100,
                    item.cacheMove.utilAvgX100,
                    item.cacheMove.utilMinX100,
                    item.cacheMove.utilMaxX100,
                    item.swLatency.enabled,
                    item.swLatency.total,
                    item.swLatency.sampled,
                    item.swLatency.avgNs,
                    item.swLatency.p90Ns,
                    item.swLatency.p99Ns,
                    item.swLatency.maxNs,
                    item.directReclaimTotal,
                    item.directReclaimFgTotal,
                    item.directReclaimSampled,
                    item.directReclaimRankN,
                    item.directReclaimAvgNs,
                    item.directReclaimP10Ns,
                    item.directReclaimP20Ns,
                    item.directReclaimP30Ns,
                    item.directReclaimP40Ns,
                    item.directReclaimP50Ns,
                    item.directReclaimP60Ns,
                    item.directReclaimP70Ns,
                    item.directReclaimP80Ns,
                    item.directReclaimP90Ns,
                    item.directReclaimP99Ns,
                    item.directReclaimMaxNs,
                    byteRateMbPerSecond(item.hhReadInBytes, previous?.hhReadInBytes, elapsedMs),
                    byteRateMbPerSecond(item.hhWriteUfsBytes, previous?.hhWriteUfsBytes, elapsedMs),
                ).joinToString(",") { value->
                    escapeCsv(value.toString())
                }
            )
        }
    }
}

/** 累计计数 -> MB/s；使用实际采样时间，计数 reset/时间倒退时不产生负带宽。
 * MB 按 1024 KB 换算；浮点计算保留低于 1 MB/s 的流量，避免整数截断。
 */
internal fun counterRateMbPerSecond(current: Long, previous: Long?, elapsedMs: Long, kbPerUnit: Long): Double {
    if (previous == null || elapsedMs <= 0L || current < previous) return 0.0
    return (current - previous).toDouble() * kbPerUnit * 1000.0 / elapsedMs / 1024.0
}

/** 累计字节数 -> MB/s；使用实际采样时间，计数 reset/时间倒退时不产生负带宽。 */
internal fun byteRateMbPerSecond(current: Long, previous: Long?, elapsedMs: Long): Double {
    if (previous == null || elapsedMs <= 0L || current < previous) return 0.0
    return (current - previous).toDouble() * 1000.0 / elapsedMs / (1024.0 * 1024.0)
}
