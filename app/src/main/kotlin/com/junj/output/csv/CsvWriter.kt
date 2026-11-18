package com.junj.output.csv

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
    extentSizeKb: Int,
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
    extentSizeKb: Int,
) {
    outputFile.parentFile?.mkdirs()

    outputFile.bufferedWriter(Charsets.UTF_8).use { writer ->
        writer.appendLine(
            listOf(
                "sampleStamp(ms)",
                "extentSizeKb",
                "memTotal(KB)",
                "memFree(KB)",
                "memAvailable(KB)",
                "swapTotal(KB)",
                "swapFree(KB)",
                "swapCached(KB)",
                "psiSome(ms)",
                "psiFull(ms)",
                "vmstatR/runnableProcesses",
                "vmstatB/blockedProcesses",
                "vmstatSwpd/swapUsed(KB)",
                "vmstatFree/freeMemory(KB)",
                "vmstatBuff/bufferMemory(KB)",
                "vmstatCache/cacheMemory(KB)",
                "vmstatSi/swapInBw(KB/s)",
                "vmstatSo/swapOutBw(KB/s)",
                "vmstatBi/blockInput(KB/s)",
                "vmstatBo/blockOutput(KB/s)",
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
                "zramBdCount",
                "zramBdReads",
                "zramBdWrites",
                "zramBdReadBw(KB/s)",
                "zramBdWriteBw(KB/s)",
                "zswapPoolLimitHit",
                "zswapWrittenBackPages",
                "zswapWriteBw(KB/s)",
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
                "hhReadBw(KB/s)",
                "hhWriteBw(KB/s)",
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
            ).joinToString(",")
        )

        results.forEachIndexed { index, item ->
            writer.appendLine(
                listOf(
                    item.sampleStamp,
                    extentSizeKb,
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
                    // TODO(stats): 按原始 4KB 块数计算才正确；当前采集值已除以 1024，
                    // 因此带宽约小 1024 倍。修复时同时处理首行没有真实基线的带宽。
                    if (index == 0) item.zramBdReads * 4 * 1024 / sampleIntervalMs else (item.zramBdReads - results[index - 1].zramBdReads) * 4 * 1024 / sampleIntervalMs,
                    if (index == 0) item.zramBdWrites * 4 * 1024 / sampleIntervalMs else (item.zramBdWrites - results[index - 1].zramBdWrites) * 4 * 1024 / sampleIntervalMs,
                    item.zswapPoolLimitHit,
                    item.zswapWrittenBackPages,
                    if (index == 0) (item.zswapPoolLimitHit + item.zswapWrittenBackPages) * 4 * 1024 / sampleIntervalMs
                    else (item.zswapPoolLimitHit + item.zswapWrittenBackPages - results[index - 1].zswapPoolLimitHit - results[index - 1].zswapWrittenBackPages) * 4 * 1024 / sampleIntervalMs,
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
                    if (item.hhPfHitObjs + item.hhPfNeverUsedObjs > 0)
                        item.hhPfHitObjs * 100 / (item.hhPfHitObjs + item.hhPfNeverUsedObjs) else 0,
                    
                    item.hhPfDemandGroups,
                    item.hhPfDemandObjs,
                    item.hhPfDemandHitObjs,
                    item.hhPfDemandNeverObjs,
                    item.hhPfDemandHitBytes,
                    if (item.hhPfObjs > 0)
                        item.hhPfHitObjs * 100 / item.hhPfObjs
                    else 0,
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
                    if (index == 0) item.hhReadInBytes / sampleIntervalMs
                    else (item.hhReadInBytes - results[index - 1].hhReadInBytes) / sampleIntervalMs,
                    if (index == 0) item.hhWriteUfsBytes / sampleIntervalMs
                    else (item.hhWriteUfsBytes - results[index - 1].hhWriteUfsBytes) / sampleIntervalMs,
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
                ).joinToString(",") { value->
                    escapeCsv(value.toString())
                }
            )
        }
    }
}
