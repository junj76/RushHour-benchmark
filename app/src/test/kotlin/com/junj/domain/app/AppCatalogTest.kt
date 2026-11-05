package com.junj.domain.app

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class AppCatalogTest {
    @Test
    fun `workloads grow by one entry and keep shorts then youtube in the base set`() {
        assertEquals(listOf("youtube_shorts", "youtube"), globalAppInfos.take(2).map { it.name })
        assertEquals(17, globalAppInfos.size)
        assertEquals(17, globalAppInfos.map { it.name }.distinct().size)
        for (count in 10..17) {
            val workload = globalAppInfos.take(count)
            assertEquals(count, workload.size)
            assertTrue(workload.take(2).all { it.packageName == "com.google.android.youtube" })
            if (count > 10) assertEquals(globalAppInfos.take(count - 1), workload.dropLast(1))
        }
    }
}
