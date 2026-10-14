package com.junj.output.csv

import com.junj.domain.ExperimentResults
import com.junj.domain.launch.LaunchApplicationItem
import com.junj.domain.metrics.SamplingItem
import com.junj.domain.survival.AppSurvivalResult
import com.junj.output.ExperimentOutputPaths
import java.io.File

fun saveCsv(results: ExperimentResults, output: ExperimentOutputPaths, sampleIntervalMs: Long) {
    saveLaunchResultsToCsv(
        results.launches,
        output.launchCsv,
    )
    saveSampleResultsToCsv(
        results.samples,
        output.sampleCsv,
        sampleIntervalMs,
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
) {
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
                "hhPfDemandHitRateX100",
                "hhPfCachePages",
                "hhPfCachePagesPeak",
                "hhInflightPages",
                "hhInflightPagesPeak",
                "hhMovedInBytes",
                "hhMovedInPages",
                "hhCachePages",
                "hhCachePagesPeak",
                "hhReadBw(KB/s)",
                "hhWriteBw(KB/s)",
                "swLatEnabled",
                "swLatTotal",
                "swLatSampled",
                "swLatAvgNs",
                "swLatP90Ns",
                "swLatP99Ns",
                "swLatMaxNs",
            ).joinToString(",")
        )

        results.forEachIndexed { index, item ->
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
                    if (index == 0) item.zramBdReads * 4 * 1024 / sampleIntervalMs else (item.zramBdReads - results[index - 1].zramBdReads) * 4 * 1024 / sampleIntervalMs,
                    if (index == 0) item.zramBdWrites * 4 * 1024 / sampleIntervalMs else (item.zramBdWrites - results[index - 1].zramBdWrites) * 4 * 1024 / sampleIntervalMs,
                    item.zswapPoolLimitHit,
                    item.zswapWrittenBackPages,
                    if (index == 0) (item.zswapPoolLimitHit + item.zswapWrittenBackPages) * 4 * 1024 / sampleIntervalMs
                    else (item.zswapPoolLimitHit + item.zswapWrittenBackPages - results[index - 1].zswapPoolLimitHit - results[index - 1].zswapWrittenBackPages) * 4 * 1024 / sampleIntervalMs,
                    item.hhIoReqCnt,
                    item.hhIoReqBytes,
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
                    if (item.hhPfDemandHitObjs + item.hhPfDemandNeverObjs > 0)
                        item.hhPfDemandHitObjs * 100 /
                            (item.hhPfDemandHitObjs + item.hhPfDemandNeverObjs) else 0,
                    item.hhPfCachePages,
                    item.hhPfCachePagesPeak,
                    item.hhInflightPages,
                    item.hhInflightPagesPeak,
                    item.hhMovedInBytes,
                    item.hhMovedInPages,
                    item.hhCachePages,
                    item.hhCachePagesPeak,
                    if (index == 0) item.hhReadInBytes / sampleIntervalMs
                    else (item.hhReadInBytes - results[index - 1].hhReadInBytes) / sampleIntervalMs,
                    if (index == 0) item.hhWriteUfsBytes / sampleIntervalMs
                    else (item.hhWriteUfsBytes - results[index - 1].hhWriteUfsBytes) / sampleIntervalMs,
                    item.swLatEnabled,
                    item.swLatTotal,
                    item.swLatSampled,
                    item.swLatAvgNs,
                    item.swLatP90Ns,
                    item.swLatP99Ns,
                    item.swLatMaxNs,
                ).joinToString(",") { value->
                    escapeCsv(value.toString())
                }
            )
        }
    }
}
