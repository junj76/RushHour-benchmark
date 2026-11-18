package com.junj.output.reporting

import com.junj.cli.parseArgs
import com.junj.config.ExperimentConfig
import com.junj.output.logging.Logger
import java.io.File
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertTrue

class RunHeaderTest {
    @Test
    fun `both zswap variants record flash size and max pool percent in the header`() {
        for ((type, label) in listOf("4" to "zswap", "5" to "zswap(zbud)")) {
            for (options in listOf(emptyArray<String>(), arrayOf("-f", "2048", "-m", "5"))) {
                val directory = Files.createTempDirectory("zswap-header-test").toFile()
                try {
                    val config = parseArgs(arrayOf("-t", type, "-a", "2") + options)
                    Logger(directory).use { logger ->
                        logRunHeader(logger, config, listOf("bilibili", "wps"), directory)
                    }
                    val text = File(directory, "summary.txt").readText()
                    assertTrue(text.contains("run.id=${config.timestamp}"), text)
                    assertTrue(config.timestamp.endsWith("_workload2_${label}${config.flashSwapDeviceSizeMB}_m${config.zswapMaxPoolPercent}"))
                    assertTrue(text.contains("config.swapType=$type"), text)
                    assertTrue(text.contains("config.flashSwapMiB=${config.flashSwapDeviceSizeMB}"), text)
                    assertTrue(text.contains("config.zswapMaxPoolPercent=${config.zswapMaxPoolPercent}"), text)
                    assertTrue(text.contains("config.writebackIntervalSec=-"), text)
                } finally {
                    directory.deleteRecursively()
                }
            }
        }
    }

    @Test
    fun `writes schema, run and config sections before the test starts`() {
        val directory = Files.createTempDirectory("header-test").toFile()
        try {
            Logger(directory).use { logger ->
                logRunHeader(
                    logger = logger,
                    config = ExperimentConfig(
                        swapType = 1,
                        appCount = 2,
                        randomSeed = 0,
                        timestamp = "20261016_120000_workload2_onlyZram",
                        outputDirectory = directory,
                        flashSwapDeviceSizeMB = 4096,
                    ),
                    appNames = listOf("bilibili", "wps"),
                    outputDirectory = directory,
                )
            }

            val text = File(directory, "summary.txt").readText()

            assertTrue(text.startsWith("# schema=2"), text)
            assertTrue(text.contains("[run]"), text)
            assertTrue(text.contains("run.id=20261016_120000_workload2_onlyZram"), text)
            assertTrue(text.contains("run.logsPath=${directory.path}"), text)
            assertTrue(text.contains("[config]"), text)
            assertTrue(text.contains("config.seed=0"), text)
            assertTrue(text.contains("config.appSet=2"), text)
            assertTrue(text.contains("config.appCount=2"), text)
            assertTrue(text.contains("config.workload=workload2"), text)
            assertTrue(text.contains("config.appOrder=bilibili,wps"), text)
            assertTrue(text.contains("config.swapType=1"), text)
            assertTrue(text.contains("config.testRounds=10"), text)
            // sampleSchema 已被移除：CSV 的格式由列名里的单位后缀自我描述。
            assertTrue(!text.contains("config.sampleSchema"), text)
            // 结构统一：与 type 无关的项也必须存在，只是值为 "-"（这样 comparison.csv 不会出现空白）。
            assertTrue(text.contains("config.flashSwapMiB=-"), text)
            assertTrue(text.contains("config.writebackIntervalSec=-"), text)
            assertTrue(text.contains("config.zswapMaxPoolPercent=-"), text)
            assertTrue(text.contains("config.sampleIntervalMs=2000"), text)
            assertTrue(text.contains("config.launchIntervalMs=20000"), text)
            // 头部在这里结束：结果分节由 reportSummary 稍后追加
            assertTrue(text.endsWith("config.collectDelayMs=18000\n"), text)
        } finally {
            directory.deleteRecursively()
        }
    }
}
