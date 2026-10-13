package com.junj.device.pid

import com.junj.device.adb.AdbExecutor

fun getApplicationPid(adb: AdbExecutor, packageName: String): Long? {
    val result = adb.rootShell("pidof $packageName")
    if (result.exitCode != 0) return null

    return result.output
        .trim()
        .split(Regex("""\s+"""))
        .firstNotNullOfOrNull { it.toLongOrNull() }
}

fun waitForApplicationPid(
    adb: AdbExecutor,
    packageName: String,
    timeoutMs: Long = 2_000L,
    pollIntervalMs: Long = 100L,
): Long? {
    val deadlineNs = System.nanoTime() + timeoutMs * 1_000_000L
    do {
        getApplicationPid(adb, packageName)?.let { return it }
        Thread.sleep(pollIntervalMs)
    } while (System.nanoTime() < deadlineNs)

    return null
}

fun isApplicationProcessAlive(
    adb: AdbExecutor,
    packageName: String,
    pid: Long?,
): Boolean {
    if (pid == null) return false

    val result = adb.rootShell("cat /proc/$pid/cmdline")
    if (result.exitCode != 0) return false

    return result.output
        .substringBefore('\u0000')
        .trim() == packageName
}
