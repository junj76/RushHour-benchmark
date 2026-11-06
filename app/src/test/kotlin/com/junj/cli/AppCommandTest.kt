package com.junj.cli

import com.junj.config.DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB
import com.junj.config.DEFAULT_ZRAM_WRITEBACK_INTERVAL_SEC
import com.junj.config.DEFAULT_ZSWAP_MAX_POOL_PERCENT
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

// Code mapping (declaration order in ArgType):
//   0 = noSwap, 1 = onlyZram, 2 = zramWriteback, 3 = flashSwap, 4 = zswap, 5 = zswap(zbud)
class AppCommandTest {
    @Test
    fun `workload counts ten through seventeen are recorded directly`() {
        for (count in 10..17) {
            val config = parseArgs(arrayOf("-t", "1", "-a", count.toString()))
            assertEquals(count, config.appCount)
            assertTrue(config.timestamp.endsWith("_workload${count}_onlyZram"))
        }
    }

    @Test
    fun `short run accepts one round while ordinary runs keep ten`() {
        assertEquals(10, parseArgs(arrayOf("-t", "3", "-a", "17")).testRoundCount)
        assertEquals(1, parseArgs(arrayOf("-t", "3", "-a", "17", "--rounds", "1")).testRoundCount)
    }

    @Test
    fun `flash size falls back to the default when -f is omitted`() {
        val config = parseArgs(arrayOf("-t", "3", "-a", "6"))

        assertEquals(DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB, config.flashSwapDeviceSizeMB)
    }

    @Test
    fun `flash size is taken from -f`() {
        val config = parseArgs(arrayOf("-t", "3", "-a", "6", "-f", "2048"))

        assertEquals(2048, config.flashSwapDeviceSizeMB)
    }

    @Test
    fun `flash size shows up right after the flash swap suffix`() {
        assertTrue(
            parseArgs(arrayOf("-t", "3", "-a", "6", "-f", "2048"))
                .timestamp.endsWith("_workload6_flashSwap2048")
        )
        assertTrue(
            parseArgs(arrayOf("-t", "4", "-a", "10"))
                .timestamp.endsWith("_workload10_zswap${DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB}_m$DEFAULT_ZSWAP_MAX_POOL_PERCENT")
        )
    }

    @Test
    fun `swap types without flash swap keep the suffix without a size`() {
        assertTrue(parseArgs(arrayOf("-t", "0", "-a", "6")).timestamp.endsWith("_workload6_noSwap"))
        assertTrue(parseArgs(arrayOf("-t", "1", "-a", "6")).timestamp.endsWith("_workload6_onlyZram"))
    }

    @Test
    fun `flash size is rejected for swap types that cannot use flash swap`() {
        assertFailsWith<IllegalArgumentException> {
            parseArgs(arrayOf("-t", "0", "-a", "6", "-f", "2048"))
        }
        assertFailsWith<IllegalArgumentException> {
            parseArgs(arrayOf("-t", "1", "-a", "6", "-f", "2048"))
        }
    }

    @Test
    fun `flash size must be positive`() {
        assertFailsWith<IllegalArgumentException> {
            parseArgs(arrayOf("-t", "3", "-a", "6", "-f", "0"))
        }
        assertFailsWith<IllegalArgumentException> {
            parseArgs(arrayOf("-t", "3", "-a", "6", "-f", "-1"))
        }
    }

    @Test
    fun `type codes follow the declaration order`() {
        assertEquals(0, ArgType.NO_SWAP.code)
        assertEquals(1, ArgType.ONLY_ZRAM.code)
        assertEquals(2, ArgType.ZRAM_WRITEBACK.code)
        assertEquals(3, ArgType.ONLY_FLASH_SWAP.code)
        assertEquals(4, ArgType.ZSWAP.code)
        assertEquals(5, ArgType.ZSWAP_ZBUD.code)
        assertEquals(ArgType.ZSWAP_ZBUD, ArgType.fromCode(5))
    }

    @Test
    fun `zram writeback defaults to the default backing size and interval`() {
        val config = parseArgs(arrayOf("-t", "2", "-a", "6"))

        assertEquals(DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB, config.flashSwapDeviceSizeMB)
        assertEquals(DEFAULT_ZRAM_WRITEBACK_INTERVAL_SEC, config.zramWritebackIntervalSec)
        assertTrue(
            config.timestamp.endsWith("_workload6_zramWriteback4096_wb${DEFAULT_ZRAM_WRITEBACK_INTERVAL_SEC}s")
        )
    }

    @Test
    fun `zram writeback takes the backing size from -f and the interval from -w`() {
        val config = parseArgs(arrayOf("-t", "2", "-a", "17", "-f", "1024", "-w", "30"))

        assertEquals(1024, config.flashSwapDeviceSizeMB)
        assertEquals(30, config.zramWritebackIntervalSec)
        assertTrue(config.timestamp.endsWith("_workload17_zramWriteback1024_wb30s"))
    }

    @Test
    fun `writeback interval is rejected for swap types that do not write back`() {
        assertFailsWith<IllegalArgumentException> {
            parseArgs(arrayOf("-t", "1", "-a", "6", "-w", "30"))
        }
        for (type in listOf("4", "5")) {
            assertFailsWith<IllegalArgumentException> {
                parseArgs(arrayOf("-t", type, "-a", "6", "-w", "30"))
            }
        }
    }

    @Test
    fun `writeback interval must be positive`() {
        assertFailsWith<IllegalArgumentException> {
            parseArgs(arrayOf("-t", "2", "-a", "6", "-w", "0"))
        }
        assertFailsWith<IllegalArgumentException> {
            parseArgs(arrayOf("-t", "2", "-a", "6", "-w", "-10"))
        }
    }

    @Test
    fun `zswap max pool percent comes from -m and defaults to 20`() {
        for ((type, label) in listOf("4" to "zswap", "5" to "zswap(zbud)")) {
            val defaults = parseArgs(arrayOf("-t", type, "-a", "10"))
            assertEquals(type.toInt(), defaults.swapType)
            assertEquals(DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB, defaults.flashSwapDeviceSizeMB)
            assertEquals(DEFAULT_ZSWAP_MAX_POOL_PERCENT, defaults.zswapMaxPoolPercent)
            assertTrue(
                defaults.timestamp.endsWith("_workload10_${label}${DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB}_m$DEFAULT_ZSWAP_MAX_POOL_PERCENT"),
                defaults.timestamp,
            )

            val config = parseArgs(arrayOf("-t", type, "-a", "10", "-f", "2048", "-m", "5"))
            assertEquals(5, config.zswapMaxPoolPercent)
            assertEquals(2048, config.flashSwapDeviceSizeMB)
            assertTrue(config.timestamp.endsWith("_workload10_${label}2048_m5"), config.timestamp)
        }
    }

    @Test
    fun `max pool percent is rejected outside zswap and outside one to hundred`() {
        assertFailsWith<IllegalArgumentException> { parseArgs(arrayOf("-t", "1", "-a", "6", "-m", "5")) }
        assertFailsWith<IllegalArgumentException> { parseArgs(arrayOf("-t", "2", "-a", "6", "-m", "5")) }
        for (type in listOf("4", "5")) {
            for (percent in listOf("0", "101")) {
                assertFailsWith<IllegalArgumentException> {
                    parseArgs(arrayOf("-t", type, "-a", "6", "-m", percent))
                }
            }
        }
    }

    @Test
    fun `zswap takes the flash swap size from -f`() {
        for ((type, label) in listOf("4" to "zswap", "5" to "zswap(zbud)")) {
            val config = parseArgs(arrayOf("-t", type, "-a", "10", "--flash_size", "2048"))
            assertEquals(2048, config.flashSwapDeviceSizeMB)
            assertTrue(config.timestamp.endsWith("_workload10_${label}2048_m$DEFAULT_ZSWAP_MAX_POOL_PERCENT"), config.timestamp)
            for (size in listOf("0", "-1")) {
                assertFailsWith<IllegalArgumentException> {
                    parseArgs(arrayOf("-t", type, "-a", "10", "-f", size))
                }
            }
            for (percent in listOf("1", "100")) {
                assertEquals(
                    percent.toInt(),
                    parseArgs(arrayOf("-t", type, "-a", "10", "--max_pool_percent", percent)).zswapMaxPoolPercent,
                )
            }
        }
    }
}
