package com.junj.device.pid

import com.junj.device.adb.AdbExecutor

fun getApplicationPid(adb: AdbExecutor, processName: String): Long? {
    val result = adb.rootShell("pidof $processName") { result ->
        result.exitCode == 1 && result.output.isBlank()
    }
    if (result.exitCode != 0) return null

    return result.output
        .trim()
        .split(Regex("""\s+"""))
        .firstNotNullOfOrNull { it.toLongOrNull() }
}

fun waitForApplicationPid(
    adb: AdbExecutor,
    processName: String,
    timeoutMs: Long = 2_000L,
    pollIntervalMs: Long = 100L,
): Long? {
    val deadlineNs = System.nanoTime() + timeoutMs * 1_000_000L
    do {
        getApplicationPid(adb, processName)?.let { return it }
        Thread.sleep(pollIntervalMs)
    } while (System.nanoTime() < deadlineNs)

    return null
}

fun isApplicationProcessAlive(
    adb: AdbExecutor,
    processName: String,
    pid: Long?,
): Boolean {
    if (pid == null) return false

    val path = "/proc/$pid/cmdline"
    val result = adb.rootShell("cat $path") { result ->
        result.exitCode == 1 && result.output.trim() == "cat: $path: No such file or directory"
    }
    if (result.exitCode != 0) return false

    return result.output
        .substringBefore('\u0000')
        .trim() == processName
}
