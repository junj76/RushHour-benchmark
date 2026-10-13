package com.junj.device.pid

import com.junj.device.adb.AdbExecutor
import com.junj.device.adb.CommandResult
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ApplicationPidTest {
    @Test
    fun `returns pid from numeric pidof output`() {
        val adb = FakeAdb(mapOf("pidof com.example" to CommandResult(0, "1234\n")))

        assertEquals(1234L, getApplicationPid(adb, "com.example"))
    }

    @Test
    fun `returns null instead of zero for adb error text`() {
        val adb = FakeAdb(mapOf("pidof com.example" to CommandResult(0, "adb.exe: device offline")))

        assertNull(getApplicationPid(adb, "com.example"))
    }

    @Test
    fun `checks that original pid still belongs to package`() {
        val matchingAdb = FakeAdb(
            mapOf("cat /proc/1234/cmdline" to CommandResult(0, "com.example\u0000"))
        )
        val reusedPidAdb = FakeAdb(
            mapOf("cat /proc/1234/cmdline" to CommandResult(0, "com.other\u0000"))
        )

        assertTrue(isApplicationProcessAlive(matchingAdb, "com.example", 1234L))
        assertFalse(isApplicationProcessAlive(reusedPidAdb, "com.example", 1234L))
    }

    private class FakeAdb(
        private val rootResults: Map<String, CommandResult>,
    ) : AdbExecutor {
        override fun shell(command: String): CommandResult = error("Unexpected shell command: $command")

        override fun rootShell(command: String): CommandResult =
            rootResults[command] ?: CommandResult(1, "missing fake result")
    }
}
