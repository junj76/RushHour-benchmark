package com.junj.output.csv

import com.junj.domain.metrics.SamplingItem
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class CsvWriterTest {
    @Test
    fun `flash KB reports interval volumes and ignores missing samples and resets`() {
        val initial = sample(0).copy(flashDeviceReadKb = 100.0, flashDeviceWriteKb = 200.0)
        val next = initial.copy(sampleStamp = 2000, flashDeviceReadKb = 107.5, flashDeviceWriteKb = 211.0)
        val rows = csvRows(listOf(initial, next, sample(4000), next.copy(sampleStamp = 6000),
            initial.copy(sampleStamp = 8000)))
        assertEquals(listOf("0.0", "7.5", "0.0", "0.0", "0.0"), rows.map { it["flashDeviceRead(KB/interval)"] })
        assertEquals(listOf("0.0", "11.0", "0.0", "0.0", "0.0"), rows.map { it["flashDeviceWrite(KB/interval)"] })
    }

    @Test
    fun `sample csv header and every data row have the same column count`() {
        val file = File.createTempFile("sample", ".csv")
        try {
            saveSampleResultsToCsv(
                listOf(sample(stamp = 0, writtenBack = 0), sample(stamp = 2_000, writtenBack = 4)),
                file,
                2_000,
            )

            val lines = file.readLines().filter { it.isNotBlank() }
            assertEquals(3, lines.size, "expected one header line plus two data rows")

            val headerColumns = lines.first().split(",").size
            lines.drop(1).forEach { row ->
                assertEquals(headerColumns, row.split(",").size, "column count mismatch in row: $row")
            }
        } finally {
            file.delete()
        }
    }

    @Test
    fun `zswap write back rate only counts pages written back from the pool`() {
        val file = File.createTempFile("sample", ".csv")
        try {
            // pool_limit_hit 说的是「被池拒绝、直接写进 swap 设备」的页，与回写无关，
            // 这里给它一个会变化的假值：旧实现把它一起算进速率，本用例会失败。
            saveSampleResultsToCsv(
                listOf(
                    sample(stamp = 0, writtenBack = 0, limitHit = 5),
                    sample(stamp = 2_000, writtenBack = 4, limitHit = 1_000),
                ),
                file,
                2_000,
            )

            val rows = file.readLines().filter { it.isNotBlank() }.drop(1)
            val column = file.readLines().first().split(",").indexOf("zswapWriteBw(MB/s)")
            assertEquals(0.0, rows[0].split(",")[column].toDouble())
            // 4 页 × 4 KB / 2s / 1024 = 0.0078125 MB/s；不能整数截断成 0。
            assertEquals(0.0078125, rows[1].split(",")[column].toDouble())
        } finally {
            file.delete()
        }
    }

    @Test
    fun `csv explicitly labels four KB counters MB per second and microsecond PSI`() {
        val rows = csvRows(listOf(sample(0).copy(
            zramBdCount = 1_048_448,
            zramBdReads = 380_100,
            zramBdWrites = 2_691_376,
            vmstatSi = 1.5,
            vmstatSo = 0.25,
            vmstatBi = 1.0,
            vmstatBo = 2.0,
        )))
        val row = rows.single()
        assertEquals("1048448", row["zramBdCount(KB)"])
        assertEquals("380100", row["zramBdReads(KB)"])
        assertEquals("2691376", row["zramBdWrites(KB)"])
        assertEquals("1.5", row["vmstatSi/swapInBw(KB/s)"])
        assertEquals("0.25", row["vmstatSo/swapOutBw(KB/s)"])
        assertEquals("1.0", row["vmstatBi/blockInput(blocks/s)"])
        assertEquals("2.0", row["vmstatBo/blockOutput(blocks/s)"])
        assertEquals("1343844", row["zswapPoolTotalSize(KB)"])
        assertEquals("1000000", row["psiSome(us)"])
        assertEquals("500000", row["psiFull(us)"])
        assertTrue("zramBdCount(KB)" in row)
        assertTrue(row.keys.none { "TotalSize(B)" in it }, row.keys.toString())
        // vmstat counts si/so in KB/s on Linux; the header must state that, not "MB/s".
        assertTrue(row.keys.any { it.startsWith("vmstatSi") && it.contains("(KB/s)") }, row.keys.toString())
        assertTrue(row.keys.any { it.startsWith("vmstatSo") && it.contains("(KB/s)") }, row.keys.toString())
    }

    @Test
    fun `backing bandwidth uses actual sample delta and preserves fractional MB per second`() {
        val initial = sample(1_000).copy(zramBdReads = 10_000, zramBdWrites = 20_000)
        val next = initial.copy(sampleStamp = 4_000, zramBdReads = 11_024, zramBdWrites = 22_048)
        val rows = csvRows(listOf(initial, next), intervalMs = 2_000)
        assertEquals(0.0, rows[0].getValue("zramBdReadBw(MB/s)").toDouble())
        assertEquals(0.0, rows[0].getValue("zramBdWriteBw(MB/s)").toDouble())
        // 实际间隔 3 秒（不是配置的 2 秒）；1024 KB = 1 MB。
        assertEquals(1.0 / 3.0, rows[1].getValue("zramBdReadBw(MB/s)").toDouble(), 1e-12)
        assertEquals(2.0 / 3.0, rows[1].getValue("zramBdWriteBw(MB/s)").toDouble(), 1e-12)
    }

    @Test
    fun `counter resets and non increasing timestamps produce zero bandwidth`() {
        val initial = sample(2_000, writtenBack = 200).copy(zramBdReads = 300, zramBdWrites = 400)
        val reset = sample(4_000, writtenBack = 1).copy(zramBdReads = 2, zramBdWrites = 3)
        val sameTime = reset.copy(zramBdReads = 200, zramBdWrites = 300, zswapWrittenBackPages = 400)
        val backwards = sameTime.copy(sampleStamp = 3_000, zramBdReads = 400, zramBdWrites = 500, zswapWrittenBackPages = 600)
        val rows = csvRows(listOf(initial, reset, sameTime, backwards))
        rows.forEach { row ->
            listOf("zramBdReadBw(MB/s)", "zramBdWriteBw(MB/s)", "zswapWriteBw(MB/s)").forEach { column ->
                assertEquals(0.0, row.getValue(column).toDouble(), column)
            }
        }
    }

    @Test
    fun `zswap sizes and bandwidth use kernel page size and bd rate follows KB`() {
        val initial = sample(0, writtenBack = 20).copy(pageSizeKb = 16)
        val next = initial.copy(sampleStamp = 2_000, zswapWrittenBackPages = 24, zramBdReads = 16)
        val rows = csvRows(listOf(initial, next))
        assertEquals((685_822L * 16L).toString(), rows[1]["zswapStoredSize(KB)"])
        assertEquals("384", rows[1]["zswapWrittenBackSize(KB)"])
        assertEquals(0.03125, rows[1].getValue("zswapWriteBw(MB/s)").toDouble())
        assertEquals(0.0078125, rows[1].getValue("zramBdReadBw(MB/s)").toDouble())
    }

    @Test
    fun `zswap page size changes invalidate the bandwidth interval`() {
        val rows = csvRows(listOf(
            sample(0, writtenBack = 20).copy(pageSizeKb = 4),
            sample(2_000, writtenBack = 24).copy(pageSizeKb = 16),
        ))
        assertEquals(0.0, rows[1].getValue("zswapWriteBw(MB/s)").toDouble())
    }

    private fun csvRows(samples: List<SamplingItem>, intervalMs: Long = 2_000): List<Map<String, String>> {
        val file = File.createTempFile("sample-units", ".csv")
        return try {
            saveSampleResultsToCsv(samples, file, intervalMs)
            val lines = file.readLines()
            val headers = lines.first().split(",")
            lines.drop(1).map { headers.zip(it.split(",")).toMap() }
        } finally {
            file.delete()
        }
    }

    private fun sample(
        stamp: Long,
        writtenBack: Long = 0,
        limitHit: Long = 0,
    ) = SamplingItem(
        sampleStamp = stamp,
        meminfoMemTotal = 7_737_752,
        meminfoMemFree = 400_000,
        meminfoMemAvailable = 2_000_000,
        meminfoSwapTotal = 4_194_300,
        meminfoSwapFree = 1_000_000,
        meminfoSwapCached = 4_000,
        psiSome = 1_000_000,
        psiFull = 500_000,
        vmstatR = 1,
        vmstatB = 0,
        vmstatSwpd = 3_000_000,
        vmstatFree = 400_000,
        vmstatBuff = 1_000,
        vmstatCache = 2_000_000,
        vmstatSi = 0.0,
        vmstatSo = 0.0,
        vmstatBi = 0.0,
        vmstatBo = 0.0,
        vmstatIn = 1_000,
        vmstatCs = 2_000,
        vmstatUs = 30,
        vmstatSy = 40,
        vmstatId = 30,
        vmstatWa = 0,
        bigTemp = 55.0,
        midTemp = 56.0,
        littleTemp = 57.0,
        socThermTemp = 50.0,
        virtualSkinTemp = 42.0,
        zramOrigDataSize = 0,
        zramComprDataSize = 0,
        zramMemUsedTotal = 0,
        zramMemUsedMax = 0,
        zramBdCount = 0,
        zramBdReads = 0,
        zramBdWrites = 0,
        zswapStoredPages = 685_822,
        zswapPoolTotalSize = 1_343_844, // KB，不是原始字节数。
        zswapPoolLimitHit = limitHit,
        zswapWrittenBackPages = writtenBack,
    )
}
