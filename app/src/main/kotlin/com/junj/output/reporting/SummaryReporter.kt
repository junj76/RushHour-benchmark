package com.junj.output.reporting

import com.junj.domain.launch.LaunchApplicationItem
import com.junj.domain.metrics.SamplingItem
import com.junj.domain.survival.AppSurvivalResult
import com.junj.output.logging.LogType
import com.junj.output.logging.Logger

data class ExperimentSummary(
    val logsPath: String,
    val coldLaunchCount: Int,
    val warmLaunchCount: Int,
    val hotLaunchCount: Int,
    val unknownLaunchCount: Int,
    val averageResponseLatency: Long,
    val lmkdCount: Int,
    val appAliveRatio: Double,
    val appCurrentlyRunningRatio: Double,
    val bigTemperatureAverage: Double,
    val midTemperatureAverage: Double,
    val littleTemperatureAverage: Double,
    val socThermTemperatureAverage: Double,
    val virtualSkinTemperatureAverage: Double,
    val psiSomeDeltaMs: Long,
    val psiFullDeltaMs: Long,
)

fun calculateSummary(
    launches: List<LaunchApplicationItem>,
    samples: List<SamplingItem>,
    survivals: List<AppSurvivalResult>,
    appCount: Int,
    testRoundCount: Int,
    lmkdCount: Int,
    logsPath: String,
): ExperimentSummary {
    var cold = 0
    var warm = 0
    var hot = 0
    var unknown = 0
    var totalResponseLatency = 0L

    launches.forEach { result ->
        when (result.amStartLaunchState) {
            "COLD" -> cold++
            "WARM" -> warm++
            "HOT" -> hot++
            "UNKNOWN (0)" -> unknown++
            else -> Unit
        }
        totalResponseLatency += result.amStartTotalTime
    }

    val sampleCount = samples.size.coerceAtLeast(1)
    val firstSample = samples.firstOrNull()
    val lastSample = samples.lastOrNull()
    val divisor = (testRoundCount * appCount).coerceAtLeast(1)
    val survivalCount = survivals.size.coerceAtLeast(1)

    return ExperimentSummary(
        logsPath = logsPath,
        coldLaunchCount = cold,
        warmLaunchCount = warm,
        hotLaunchCount = hot,
        unknownLaunchCount = unknown,
        averageResponseLatency = totalResponseLatency / divisor,
        lmkdCount = lmkdCount,
        appAliveRatio = survivals.count { it.originalProcessAlive }.toDouble() / survivalCount,
        appCurrentlyRunningRatio = survivals.count { it.appCurrentlyRunning }.toDouble() / survivalCount,
        bigTemperatureAverage = samples.sumOf { it.bigTemp } / sampleCount,
        midTemperatureAverage = samples.sumOf { it.midTemp } / sampleCount,
        littleTemperatureAverage = samples.sumOf { it.littleTemp } / sampleCount,
        socThermTemperatureAverage = samples.sumOf { it.socThermTemp } / sampleCount,
        virtualSkinTemperatureAverage = samples.sumOf { it.virtualSkinTemp } / sampleCount,
        psiSomeDeltaMs = ((lastSample?.psiSome ?: 0L) - (firstSample?.psiSome ?: 0L)) / 1000,
        psiFullDeltaMs = ((lastSample?.psiFull ?: 0L) - (firstSample?.psiFull ?: 0L)) / 1000,
    )
}

class SummaryReporter(private val logger: Logger) {
    fun report(summary: ExperimentSummary) {
        println("\n")
        logger.log(LogType.SUMMARY, "logs path: ${summary.logsPath}")
        logger.log(
            LogType.SUMMARY,
            "coldLaunchCnt: ${summary.coldLaunchCount}, " +
                "warmLaunchCNT: ${summary.warmLaunchCount}, " +
                "hotLaunchCnt: ${summary.hotLaunchCount}, " +
                "unknownLaunchCnt: ${summary.unknownLaunchCount}\n" +
                "avgResponseLat: ${summary.averageResponseLatency}ms"
        )
        logger.log(
            LogType.SUMMARY,
            "lmkdCnt: ${summary.lmkdCount}, " +
                "originalProcessAliveRatio: ${"%.2f".format(summary.appAliveRatio * 100)}%, " +
                "appCurrentlyRunningRatio: ${"%.2f".format(summary.appCurrentlyRunningRatio * 100)}%",
        )
        logger.log(
            LogType.SUMMARY,
            "bigTempAvg: ${"%.2f".format(summary.bigTemperatureAverage)}, " +
                "midTempAvg: ${"%.2f".format(summary.midTemperatureAverage)}, " +
                "littleTempAvg: ${"%.2f".format(summary.littleTemperatureAverage)}, " +
                "socThermTempAvg: ${"%.2f".format(summary.socThermTemperatureAverage)}, " +
                "virtualSkinTempAvg: ${"%.2f".format(summary.virtualSkinTemperatureAverage)}"
        )
        logger.log(
            LogType.SUMMARY,
            "psiSomeDelta: ${summary.psiSomeDeltaMs}ms, " +
                "psiFullDelta: ${summary.psiFullDeltaMs}ms"
        )
    }
}
