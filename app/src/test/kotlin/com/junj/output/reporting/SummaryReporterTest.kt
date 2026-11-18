package com.junj.output.reporting

import com.junj.domain.metrics.SamplingItem
import com.junj.output.logging.Logger
import java.io.File
import java.nio.file.Files
import java.util.Locale
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class SummaryReporterTest {
    private val savedLocale = Locale.getDefault()

    @AfterTest
    fun restoreLocale() {
        Locale.setDefault(savedLocale)
    }

    @Test
    fun `percentages keep a dot even under a comma-decimal locale`() {
        Locale.setDefault(Locale.GERMANY)

        val text = renderSummary(sample(originalAlive = 50, survivalTotal = 70))

        assertTrue(text.contains("survival.originalAlive=50/70(71.43%)"), text)
        assertFalse(text.contains("71,43"), "comma decimal separator leaked into summary:\n$text")
    }

    @Test
    fun `every non-empty line is a section header or a key=value pair`() {
        val lines = renderSummary(sample()).lines()

        val offenders = lines.filter {
            it.isNotBlank() && !it.startsWith("#") && !it.startsWith("[") && !it.contains('=')
        }
        assertEquals(emptyList(), offenders)

        val keys = lines.filter { it.contains('=') }.map { it.substringBefore('=') }
        assertEquals(keys.size, keys.distinct().size, "duplicate keys: $keys")
    }

    @Test
    fun `values contain neither commas nor newlines`() {
        val valueLines = renderSummary(sample()).lines().filter { it.contains('=') }

        valueLines.forEach { line ->
            val value = line.substringAfter('=')
            assertFalse(value.contains(','), "value contains a comma: $line")
            assertFalse(value.contains('\n'), "value contains a newline: $line")
        }
    }

    @Test
    fun `sections are emitted in the order of the data classes`() {
        val sections = renderSummary(sample()).lines().filter { it.startsWith("[") }

        assertEquals(
            listOf("[result]", "[launch]", "[survival]", "[memory]", "[swap]", "[compression]", "[thermal]"),
            sections,
        )
    }

    @Test
    fun `launch counts add up and raw unknown states are printed verbatim`() {
        val summary = sample()
        val launch = summary.launch
        assertEquals(launch.total, launch.cold + launch.warm + launch.hot + launch.unknown)

        val text = renderSummary(summary)

        assertTrue(text.contains("launch.total=71"), text)
        // 计数后面带本轮占比（分母 = launch.total）
        assertTrue(text.contains("launch.cold=27(38.03%)"), text)
        assertTrue(text.contains("launch.warm=20(28.17%)"), text)
        assertTrue(text.contains("launch.hot=23(32.39%)"), text)
        assertTrue(text.contains("launch.unknown=1(1.41%)"), text)
        assertTrue(text.contains("launch.unknownRaw=UNKNOWN (-1)|UNKNOWN (0)"), text)
        assertTrue(text.contains("launch.other=-"), text)
        // Order follows the launch lifecycle (cold -> warm -> hot -> unknown -> other -> total);
        // a reader should be able to scan the bucket top-down.
        val launchOrder = listOf(
            "launch.cold=",
            "launch.warm=",
            "launch.hot=",
            "launch.unknown=",
            "launch.other=",
            "launch.total=",
        )
        val positions = launchOrder.map { text.indexOf(it) }
        assertTrue(positions.all { it >= 0 }, "missing launch keys $positions in\n$text")
        assertTrue(positions == positions.sorted(), "launch keys out of order $positions in\n$text")
    }

    @Test
    fun `shares stay at zero percent when there are no launches`() {
        val summary = sample().copy(
            launch = LaunchStats(
                total = 0,
                valid = 0,
                failed = 0,
                cold = 0,
                warm = 0,
                hot = 0,
                unknown = 0,
                unknownRawStates = "",
                otherStates = "",
            ),
        )

        val text = renderSummary(summary)

        assertTrue(text.contains("launch.cold=0(0.00%)"), text)
        assertTrue(text.contains("launch.unknown=0(0.00%)"), text)
        assertFalse(text.contains("NaN"), text)
    }

    @Test
    fun `swap in latency is reported in microseconds`() {
        val text = renderSummary(sample())

        assertTrue(text.contains("swap.avgInLatUs=68"), text)      // 68491 ns
        assertTrue(text.contains("swap.p90InLatUs=28"), text)      // 28672 ns
        assertTrue(text.contains("swap.maxInLatUs=125274"), text)  // 125374374 ns
    }

    @Test
    fun `derived ratios use the measured runtime`() {
        val text = renderSummary(sample())

        assertTrue(text.contains("run.durationMs=1425000"), text)
        assertTrue(text.contains("mem.psiSomePctOfRuntime=4.47"), text)  // 63748 / 1425000
        assertTrue(text.contains("mem.lmkdKillsPerMin=14.78"), text)     // 351 / 23.75 min
    }

    @Test
    fun `zram compression ratio comes from the fullest sample`() {
        val samples = listOf(
            sampling(),                                                   // t≈0，池还是空的
            sampling(zramOrigKb = 2_621_440, zramComprKb = 1_310_720),    // 峰值：2560MiB -> 1280MiB
            sampling(zramOrigKb = 1_000, zramComprKb = 900),              // 运行末尾池被释放
        )

        val text = renderSummary(sample(engine = CompressionEngine.ZRAM, samples = samples))

        assertTrue(text.contains("compr.engine=zram"), text)
        assertTrue(text.contains("compr.ratio=0.5000"), text)          // 取峰值而不是末尾的 0.9
        assertTrue(text.contains("compr.uncompressedMiB=2560"), text)
        assertTrue(text.contains("compr.compressedMiB=1280"), text)
    }

    @Test
    fun `zswap compression ratio converts pages and accepts pool size in KB`() {
        val samples = listOf(
            sampling(
                zswapStoredPages = 655_360,                 // 655360 页 x 4KB = 2560MiB
                zswapPoolTotalSize = 1_310_720L,        // 1280MiB
            ),
        )

        val text = renderSummary(sample(engine = CompressionEngine.ZSWAP, samples = samples))

        assertTrue(text.contains("compr.engine=zswap"), text)
        assertTrue(text.contains("compr.ratio=0.5000"), text)
        assertTrue(text.contains("compr.uncompressedMiB=2560"), text)
        assertTrue(text.contains("compr.compressedMiB=1280"), text)
    }

    @Test
    fun `zswap compression honors actual kernel page size`() {
        val samples = listOf(sampling(
            zswapStoredPages = 163_840,
            zswapPoolTotalSize = 1_310_720,
        ).copy(pageSizeKb = 16))
        val text = renderSummary(sample(engine = CompressionEngine.ZSWAP, samples = samples))
        assertTrue(text.contains("compr.ratio=0.5000"), text)
        assertTrue(text.contains("compr.uncompressedMiB=2560"), text)
        assertTrue(text.contains("compr.compressedMiB=1280"), text)
    }

    @Test
    fun `compression section reports none for swap types without compression`() {
        val text = renderSummary(sample(engine = CompressionEngine.NONE, samples = listOf(sampling(zramOrigKb = 999))))

        assertTrue(text.contains("compr.engine=none"), text)
        assertTrue(text.contains("compr.ratio=-"), text)   // 不是 0，避免把"没测到"读成结论
        assertTrue(text.contains("compr.uncompressedMiB=0"), text)
    }

    @Test
    fun `compression ratio stays empty when the pool never held data`() {
        val text = renderSummary(sample(engine = CompressionEngine.ZRAM, samples = listOf(sampling())))

        assertTrue(text.contains("compr.engine=zram"), text)
        assertTrue(text.contains("compr.ratio=-"), text)
    }

    @Test
    fun `reportSummary writes exactly what it renders and returns the summary`() {
        val directory = Files.createTempDirectory("summary-test").toFile()
        try {
            val returned = Logger(directory).use { logger ->
                reportSummary(
                    logger = logger,
                    launches = emptyList(),
                    samples = emptyList(),
                    survivals = emptyList(),
                    appCount = 7,
                    testRoundCount = 10,
                    compressionEngine = CompressionEngine.NONE,
                    runtimeMs = 1_200_000,
                    lmkdCount = 42,
                    swapInLatStats = "",
                )
            }

            val written = File(directory, "summary.txt").readText()
            assertEquals(renderSummary(returned), written.trimEnd())
            assertTrue(written.contains("mem.lmkdKills=42"), written)
            assertTrue(written.contains("compr.engine=none"), written)
        } finally {
            directory.deleteRecursively()
        }
    }

    @Test
    fun `device KB totals use sampled volumes despite residual zram data`() {
        val first = sampling(zramOrigKb = 4).copy(flashDeviceReadKb = 100.0, flashDeviceWriteKb = 200.0)
        val next = first.copy(sampleStamp = 2000, flashDeviceReadKb = 107.5, flashDeviceWriteKb = 211.0)
        val summary = calculateSummary(
            launches = emptyList(), samples = listOf(first, next), survivals = emptyList(),
            appCount = 1, testRoundCount = 1, compressionEngine = CompressionEngine.NONE,
            runtimeMs = 2000, lmkdCount = 0, swapInLatStats = "",
        )
        assertEquals(7.5, summary.swap.flashDeviceReadKb)
        assertEquals(11.0, summary.swap.flashDeviceWriteKb)
        assertTrue(renderSummary(summary).contains("swap.flashDeviceReadKb=7.5"))
    }

    private fun sample(
        originalAlive: Int = 50,
        survivalTotal: Int = 70,
        engine: CompressionEngine = CompressionEngine.NONE,
        samples: List<SamplingItem> = emptyList(),
    ) = ExperimentSummary(
        run = RunStats(durationMs = 1_425_000, sampleCount = 713),
        launch = LaunchStats(
            total = 71,
            valid = 70,
            failed = 1,
            cold = 27,
            warm = 20,
            hot = 23,
            unknown = 1,
            unknownRawStates = "UNKNOWN (-1)|UNKNOWN (0)",
            otherStates = "",
        ),
        latency = LatencyStats(
            plannedAvgMs = 1155,
            validCount = 70,
            validAvgMs = 1170,
            p50Ms = 760,
            p95Ms = 2430,
            maxMs = 7198,
            coldAvgMs = 1823,
            warmAvgMs = 989,
            hotAvgMs = 575,
        ),
        survival = SurvivalStats(
            total = survivalTotal,
            originalAlive = originalAlive,
            currentlyRunning = 64,
        ),
        memory = MemoryPressureStats(
            lmkdKills = 351,
            psiSomeDeltaMs = 63_748,
            psiFullDeltaMs = 36_272,
        ),
        swap = SwapInStats(
            totalSwapIns = 2_865_812,
            sampledSwapIns = 142_952,
            avgLatNs = 68_491,
            p90LatNs = 28_672,
            p99LatNs = 180_224,
            maxLatNs = 125_274_374,
        ),
        compression = compressionStats(engine, samples),
        thermal = ThermalStats(
            bigAvgC = 58.93,
            midAvgC = 59.97,
            littleAvgC = 59.72,
            socAvgC = 50.91,
            skinAvgC = 39.91,
            soc = ThermalTrajectory(startC = 54.78, endC = 54.91, maxC = 56.36),
            skin = ThermalTrajectory(startC = 44.09, endC = 43.48, maxC = 44.12),
        ),
    )

    /** 只填与压缩率相关的字段，其余给 0。 */
    private fun sampling(
        zramOrigKb: Long = 0,
        zramComprKb: Long = 0,
        zswapStoredPages: Long = 0,
        zswapPoolTotalSize: Long = 0,
    ) = SamplingItem(
        sampleStamp = 0,
        meminfoMemTotal = 7_737_752,
        meminfoMemFree = 400_000,
        meminfoMemAvailable = 2_000_000,
        meminfoSwapTotal = 4_194_300,
        meminfoSwapFree = 1_000_000,
        meminfoSwapCached = 4_000,
        psiSome = 0,
        psiFull = 0,
        vmstatR = 0,
        vmstatB = 0,
        vmstatSwpd = 0,
        vmstatFree = 0,
        vmstatBuff = 0,
        vmstatCache = 0,
        vmstatSi = 0.0,
        vmstatSo = 0.0,
        vmstatBi = 0.0,
        vmstatBo = 0.0,
        vmstatIn = 0,
        vmstatCs = 0,
        vmstatUs = 0,
        vmstatSy = 0,
        vmstatId = 0,
        vmstatWa = 0,
        bigTemp = 0.0,
        midTemp = 0.0,
        littleTemp = 0.0,
        socThermTemp = 0.0,
        virtualSkinTemp = 0.0,
        zramOrigDataSize = zramOrigKb,
        zramComprDataSize = zramComprKb,
        zramMemUsedTotal = 0,
        zramMemUsedMax = 0,
        zramBdCount = 0,
        zramBdReads = 0,
        zramBdWrites = 0,
        zswapStoredPages = zswapStoredPages,
        zswapPoolTotalSize = zswapPoolTotalSize,
        zswapPoolLimitHit = 0,
        zswapWrittenBackPages = 0,
    )
}
