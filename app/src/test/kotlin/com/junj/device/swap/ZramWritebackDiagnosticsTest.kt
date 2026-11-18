package com.junj.device.swap

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ZramWritebackDiagnosticsTest {
    @Test
    fun `bd stat output distinguishes raw counters from KB occupancy`() {
        val text = formatZramBdStat("262112 95025 672844")
        assertTrue(text.contains("bdCount(4KB)=262112"), text)
        assertTrue(text.contains("bdReads(4KB)=95025"), text)
        assertTrue(text.contains("bdWrites(4KB)=672844"), text)
        assertTrue(text.contains("backingUsedKB=1048448"), text)
    }

    @Test
    fun `old probe AVC is not reported as current writeback error`() {
        val raw = """
            [ 813.490207] avc: denied write path=/data/per_boot/rushhour_zram_dio_probe
            [ 1500.100000] zram0: writeback error
            [ 1501.100000] unrelated message
        """.trimIndent()
        assertEquals("[ 1500.100000] zram0: writeback error", filterFreshZramKernelMessages(raw, 1499.0))
    }

    @Test
    fun `missing timestamp never presents historical AVC as fresh`() {
        assertTrue(filterFreshZramKernelMessages("[ 813.4] avc: denied zram", null).contains("historical messages omitted"))
    }
}
