package com.junj.metrics

import com.junj.device.adb.AdbExecutor
import com.junj.device.adb.CommandResult
import com.junj.output.csv.saveSampleResultsToCsv
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class MetricsCollectorTest {
    @Test
    fun `flash KB uses sector fields three and seven including half KB`() {
        val item = parseSamplingItem("@@DSH@@ FLASH_IO\n101 2 301 4 202 6 701 8 0 10 11", 2000)
        assertEquals(150.5, item.flashDeviceReadKb)
        assertEquals(350.5, item.flashDeviceWriteKb)
        assertEquals(null, parseSamplingItem("", 0).flashDeviceReadKb)
    }

    @Test
    fun `collector converts bd counters from 4 KiB units to KB`() {
        val issued = mutableListOf<String>()
        val adb = object : AdbExecutor {
            override fun shell(command: String): CommandResult = error("Expected rootShell")
            override fun rootShell(command: String): CommandResult {
                issued += command
                return CommandResult(0, fixture())
            }
        }
        val item = MetricsCollector(adb).collect(408_000)
        assertEquals(listOf(SAMPLE_SCRIPT), issued)
        assertTrue(SAMPLE_SCRIPT.contains("getconf PAGESIZE"))
        assertEquals(408_000L, item.sampleStamp)
        assertEquals(7_737_752L, item.meminfoMemTotal)
        assertEquals(1_799_236L, item.meminfoMemAvailable)
        assertEquals(3_868_872L, item.meminfoSwapTotal)
        assertEquals(2_048L, item.zramOrigDataSize)
        assertEquals(1_024L, item.zramComprDataSize)
        assertEquals(1_088L, item.zramMemUsedTotal)
        assertEquals(3_072L, item.zramMemUsedMax)
        assertEquals(1_048_448L, item.zramBdCount)
        assertEquals(380_100L, item.zramBdReads)
        assertEquals(2_691_376L, item.zramBdWrites)
        assertEquals(1_344L, item.zswapPoolTotalSize)
        assertEquals(7L, item.zswapStoredPages)
        assertEquals(11L, item.zswapWrittenBackPages)
        assertEquals(3L, item.zswapPoolLimitHit)
    }

    @Test
    fun `vmstat bandwidth is MB per second while memory remains KB and PSI remains us`() {
        val item = parseSamplingItem(fixture(), 0)
        assertEquals(4_096L, item.vmstatSwpd)
        assertEquals(8_192L, item.vmstatFree)
        assertEquals(1_024L, item.vmstatBuff)
        assertEquals(16_384L, item.vmstatCache)
        assertEquals(1.5, item.vmstatSi)
        assertEquals(0.25, item.vmstatSo)
        assertEquals(1.0, item.vmstatBi)
        assertEquals(2.0, item.vmstatBo)
        assertEquals(13_067_468L, item.psiSome)
        assertEquals(5_710_007L, item.psiFull)
    }

    @Test
    fun `nonzero bd counters are scaled to KB without truncation`() {
        val item = parseSamplingItem(fixture(bd = "108 9 274"), 0)
        assertEquals(432L, item.zramBdCount)
        assertEquals(36L, item.zramBdReads)
        assertEquals(1_096L, item.zramBdWrites)
    }

    @Test
    fun `zswap page counts use actual page size and bd counters are KB`() {
        val item = parseSamplingItem(fixture(pageSize = "16384"), 0)
        assertEquals(16L, item.pageSizeKb)
        assertEquals(112L, item.zswapStoredSizeKb)
        assertEquals(176L, item.zswapWrittenBackSizeKb)
        assertEquals(1_048_448L, item.zramBdCount)
    }

    @Test
    fun `missing or invalid optional stats fall back to zero with legacy four KB pages`() {
        val item = parseSamplingItem("", 0)
        assertEquals(0L, item.zramBdCount)
        assertEquals(0L, item.zramOrigDataSize)
        assertEquals(0L, item.zswapPoolTotalSize)
        assertEquals(0.0, item.vmstatSi)
        assertEquals(4L, item.pageSizeKb)
        val invalid = parseSamplingItem(fixture(bd = "cat: unavailable", pageSize = "getconf: not found"), 0)
        assertEquals(0L, invalid.zramBdCount)
        assertEquals(4L, invalid.pageSizeKb)
    }

    @Test
    fun `parsed nonzero counters reach CSV without a second conversion`() {
        val initial = parseSamplingItem(fixture(), 1_000)
        val next = initial.copy(
            sampleStamp = 3_000,
            zramBdReads = initial.zramBdReads + 256,
            zramBdWrites = initial.zramBdWrites + 512,
        )
        val file = File.createTempFile("collected-unit-regression", ".csv")
        try {
            saveSampleResultsToCsv(listOf(initial, next), file, 2_000)
            val lines = file.readLines()
            val headers = lines.first().split(",")
            val rows = lines.drop(1).map { headers.zip(it.split(",")).toMap() }
            assertEquals("1048448", rows[0]["zramBdCount(KB)"])
            assertEquals("1344", rows[0]["zswapPoolTotalSize(KB)"])
            assertEquals("1.5", rows[0]["vmstatSi/swapInBw(KB/s)"])
            assertEquals(0.125, rows[1].getValue("zramBdReadBw(MB/s)").toDouble())
            assertEquals(0.25, rows[1].getValue("zramBdWriteBw(MB/s)").toDouble())
        } finally {
            file.delete()
        }
    }

    private fun fixture(bd: String = "262112 95025 672844", pageSize: String = "4096") = """
        @@DSH@@ VMSTAT
        procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
        r b swpd free buff cache si so bi bo in cs us sy id wa
        1 2 4096 8192 1024 16384 1536 256 1024 2048 100 200 10 20 65 5
        @@DSH@@ MEMINFO
        MemTotal: 7737752 kB
        MemFree: 295456 kB
        MemAvailable: 1799236 kB
        SwapTotal: 3868872 kB
        SwapFree: 879300 kB
        SwapCached: 5024 kB
        @@DSH@@ PRESSURE
        some avg10=0.12 avg60=0.34 avg300=0.56 total=13067468
        full avg10=0.01 avg60=0.02 avg300=0.03 total=5710007
        @@DSH@@ THERMAL
        @@DSH@@ ZRAM_MM
        2097152 1048576 1114112 0 3145728 0 0 0 0
        @@DSH@@ ZRAM_BD
        $bd
        @@DSH@@ PAGE_SIZE
        $pageSize
        @@DSH@@ ZSWAP
        stored_pages=7
        pool_total_size=1376256
        pool_limit_hit=3
        written_back_pages=11
    """.trimIndent()
}
