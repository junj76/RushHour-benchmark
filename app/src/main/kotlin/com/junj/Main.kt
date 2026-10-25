package com.junj

import com.junj.cli.parseArgs
import com.junj.device.adb.ProcessAdbExecutor
import com.junj.device.lifecycle.disableStayAwake
import com.junj.device.lifecycle.enableStayAwake
import com.junj.device.lifecycle.rebootDevice
import com.junj.device.lifecycle.wakeAndUnlockDevice
import com.junj.device.logcat.countLmkKills
import com.junj.device.logcat.countProcessKills
import com.junj.device.logcat.startLogcatProcesses
import com.junj.device.process.destroyProcessTree
import com.junj.device.swap.initSwapByType
import com.junj.domain.ExperimentResults
import com.junj.domain.TestClock
import com.junj.domain.app.appNameSet
import com.junj.domain.app.globalAppInfos
import com.junj.experiment.ExperimentRunner
import com.junj.metrics.MetricsCollector
import com.junj.metrics.SamplingJob
import com.junj.output.ExperimentOutputPaths
import com.junj.output.csv.saveCsv
import com.junj.output.logging.CommandDiagnostics
import com.junj.output.logging.LogType
import com.junj.output.logging.Logger
import com.junj.output.reporting.SummaryReporter
import com.junj.output.reporting.calculateSummary
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.runBlocking
import kotlin.random.Random

fun main(args: Array<String>) = runBlocking {
//    rebootDevice()
    val config = parseArgs(args)
    val output = ExperimentOutputPaths(config.outputDirectory)
    output.create()
    CommandDiagnostics.attach(output.directory)
    val logger = Logger(output.directory)
    val results = ExperimentResults()
    var apps = globalAppInfos
        .filter { it.name in appNameSet[config.appSetNumber] }
        .shuffled(Random(config.randomSeed))
    logger.log(
        LogType.SUMMARY,
        "randomSeed=${config.randomSeed}, appOrder=${apps.joinToString { it.name }}",
    )

    initSwapByType(config.swapType, config.flashSwapDeviceSizeMb, logger)

    // 屏幕必须保持亮着：息屏会让 am start 的测量失真、app_actions 直接报 "Screen is off"
    wakeAndUnlockDevice(ProcessAdbExecutor)
    enableStayAwake(ProcessAdbExecutor)

    val clock = TestClock()
    val runner = ExperimentRunner(
        adb = ProcessAdbExecutor,
        apps = apps,
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
    val logcatProcesses = startLogcatProcesses(output.logcat, output.kernelLog)

    try {
        for (round in 1..config.testRoundCount) {
            runner.runTestRound(round)
            apps = apps.reversed()
        }
    } finally {
        val elapsedMs = clock.elapsedMs()
        samplingJob.cancelAndJoin()
        logcatProcesses.forEach { destroyProcessTree(it) }

        val lmkdCount = countLmkKills(output.logcat, output.kernelLog)
        //val processKillCount = countProcessKills(output.logcat, output.kernelLog)
        val summary = calculateSummary(
            launches = results.launches,
            samples = results.samples,
            survivals = results.survivals,
            appCount = apps.size,
            testRoundCount = config.testRoundCount,
            lmkdCount = lmkdCount,
            //processKillCount = processKillCount,
            logsPath = "logs/${config.timestamp}/*.log",
        )
        SummaryReporter(logger).report(summary)
        if (results.samples.isEmpty()) {
            logger.log(LogType.SUMMARY, "no samples collected: check the sampling error above")
        }
        CommandDiagnostics.printSummary()
        logger.log(LogType.SUMMARY, "Test round runtime: ${elapsedMs / 1_000}s")
        saveCsv(results, output, config.sampleIntervalMs)
        disableStayAwake(ProcessAdbExecutor)
        logger.close()
    }
}
