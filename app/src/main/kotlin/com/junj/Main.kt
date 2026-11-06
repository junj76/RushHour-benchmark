package com.junj

import com.junj.cli.ArgType
import com.junj.cli.parseArgs
import com.junj.device.adb.ProcessAdbExecutor
import com.junj.device.lifecycle.rebootDevice
import com.junj.device.lifecycle.restBeforeTest
import com.junj.device.logcat.startLogcatProcess
import com.junj.device.process.destroyProcessTree
import com.junj.device.swap.SwapController
import com.junj.device.swap.ZramWritebackJob
import com.junj.domain.ExperimentResults
import com.junj.domain.TestClock
import com.junj.domain.app.globalAppInfos
import com.junj.experiment.ExperimentRunner
import com.junj.metrics.MetricsCollector
import com.junj.metrics.SamplingJob
import com.junj.output.ExperimentOutputPaths
import com.junj.output.csv.saveCsv
import com.junj.output.logging.Logger
import com.junj.output.reporting.CompressionEngine
import com.junj.output.reporting.logRunHeader
import com.junj.output.reporting.reportSummary
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.runBlocking
import kotlin.random.Random

fun main(args: Array<String>) = runBlocking {
    val config = parseArgs(args)
    rebootDevice()
    val output = ExperimentOutputPaths(config.outputDirectory)
    output.create()
    val logger = Logger(output.directory)
    val results = ExperimentResults()
    var apps = globalAppInfos
        .take(config.appCount)
        .shuffled(Random(config.randomSeed))
    logRunHeader(logger, config, apps.map { it.name }, output.directory)

    SwapController(
        adb = ProcessAdbExecutor,
        logger = logger,
        config = config,
    ).initSwapByType()

    restBeforeTest()

    val writebackJob = if (config.swapType == ArgType.ZRAM_WRITEBACK.code) {
        ZramWritebackJob(
            adb = ProcessAdbExecutor,
            intervalSec = config.zramWritebackIntervalSec,
        ).start(this)
    } else {
        null
    }

    val clock = TestClock()
    val runner = ExperimentRunner(
        adb = ProcessAdbExecutor,
        results = results,
        logger = logger,
        config = config,
        clock = clock,
    )
    val samplingJob = SamplingJob(
        collector = MetricsCollector(ProcessAdbExecutor),
        results = results,
        logger = logger,
        intervalMs = config.sampleIntervalMs,
        clock = clock,
    ).start(this)
    val logcatProcess = startLogcatProcess(output.logcat)

    try {
//        ProcessAdbExecutor.rootShell("""am start -W -n hello.litiaotiao.app/hello.litiaotiao.app.MainActivity""")
        for (round in 1..config.testRoundCount) {
            runner.runTestRound(round, apps)
            apps = apps.reversed()
        }
    } finally {
        val elapsedMs = clock.elapsedMs()
        writebackJob?.cancelAndJoin()
        samplingJob.cancelAndJoin()
        destroyProcessTree(logcatProcess)

        val lmkdCount = output.logcat.useLines { lines -> lines.count() }
        reportSummary(
            logger = logger,
            launches = results.launches,
            samples = results.samples,
            survivals = results.survivals,
            appCount = apps.size,
            testRoundCount = config.testRoundCount,
            compressionEngine = when (config.swapType) {
                ArgType.ONLY_ZRAM.code, ArgType.ZRAM_WRITEBACK.code -> CompressionEngine.ZRAM
                ArgType.ZSWAP.code, ArgType.ZSWAP_ZBUD.code -> CompressionEngine.ZSWAP
                else -> CompressionEngine.NONE
            },
            runtimeMs = elapsedMs,
            lmkdCount = lmkdCount,
            swapInLatStats = ProcessAdbExecutor
                .rootShell("cat /sys/kernel/mm/swapin_latency/stats")
                .output,
        )
        saveCsv(results, output, config.sampleIntervalMs)
        logger.close()
    }
}
