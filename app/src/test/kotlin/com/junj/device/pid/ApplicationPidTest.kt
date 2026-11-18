package com.junj.device.pid

import com.junj.device.adb.AdbExecutor
import com.junj.device.adb.CommandResult
import com.junj.domain.app.ApplicationInfo
import com.junj.domain.app.globalAppInfos
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

    @Test
    fun `google tracks its UI process instead of the package or interactor`() {
        val google = globalAppInfos.single { it.name == "google" }
        assertEquals("com.google.android.googlequicksearchbox:googleapp", google.processName)
        val adb = FakeAdb(mapOf(
            "pidof ${google.processName}" to CommandResult(0, "30384"),
            "cat /proc/30384/cmdline" to CommandResult(0, google.processName + '\u0000'),
            "cat /proc/3092/cmdline" to CommandResult(0, google.packageName + ":interactor" + '\u0000'),
        ))
        assertEquals(30384L, waitForApplicationPid(adb, google.processName, timeoutMs = 0))
        assertTrue(isApplicationProcessAlive(adb, google.processName, 30384L))
        assertFalse(isApplicationProcessAlive(adb, google.processName, 3092L))
        assertEquals("com.example", ApplicationInfo("example", "com.example", "").processName)
    }

    @Test
    fun `missing processes are expected while transport and permission errors remain visible`() {
        val missing = FakeAdb(mapOf(
            "pidof com.example" to CommandResult(1, ""),
            "cat /proc/1234/cmdline" to CommandResult(1, "cat: /proc/1234/cmdline: No such file or directory\n"),
        ))
        assertNull(getApplicationPid(missing, "com.example"))
        assertFalse(isApplicationProcessAlive(missing, "com.example", 1234L))
        assertEquals(listOf(true, true), missing.expectedFailures)

        for (output in listOf("adb.exe: device offline", "error: no devices/emulators found", "Permission denied")) {
            val failed = FakeAdb(mapOf(
                "pidof com.example" to CommandResult(1, output),
                "cat /proc/1234/cmdline" to CommandResult(1, output),
            ))
            assertNull(getApplicationPid(failed, "com.example"))
            assertFalse(isApplicationProcessAlive(failed, "com.example", 1234L))
            assertEquals(listOf(false, false), failed.expectedFailures)
        }
    }

    private class FakeAdb(
        private val rootResults: Map<String, CommandResult>,
    ) : AdbExecutor {
        val expectedFailures = mutableListOf<Boolean>()

        override fun rootShell(command: String, expectedFailure: (CommandResult) -> Boolean): CommandResult =
            rootShell(command).also { expectedFailures += expectedFailure(it) }

        override fun shell(command: String): CommandResult = error("Unexpected shell command: $command")

        override fun rootShell(command: String): CommandResult =
            rootResults[command] ?: CommandResult(1, "missing fake result")
    }
}
