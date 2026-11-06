package com.junj.device.lifecycle

import com.junj.device.adb.runAdbRootShellCommand
import com.junj.device.adb.runAdbShellCommand
import java.util.concurrent.TimeUnit

private const val DEFAULT_REBOOT_TIMEOUT_SECONDS = 300L
private const val REBOOT_POLL_INTERVAL_MS = 1_000L
private const val SCREEN_WAKE_WAIT_MS = 1_000L
private const val KEYGUARD_DISMISS_WAIT_MS = 1_000L
private const val PRE_TEST_REST_WAIT_MS = 30_000L
private const val ANDROID_BOOT_ID_PATH = "/proc/sys/kernel/random/boot_id"

/** 24 小时：测试期间不允许息屏打断采样（息屏会改变 CPU/IO 负载与前台应用状态）。 */
private const val SCREEN_OFF_TIMEOUT_MS = 24 * 60 * 60 * 1000L

/** 点亮屏幕的尝试次数：每次都是"唤醒 + 解锁 + 回读确认"。 */
private const val WAKE_ATTEMPTS = 3

fun rebootDevice(timeoutSeconds: Long = DEFAULT_REBOOT_TIMEOUT_SECONDS) {
    require(timeoutSeconds > 0) { "timeoutSeconds must be greater than 0" }

    val bootIdBeforeReboot = runAdbShellCommand("cat $ANDROID_BOOT_ID_PATH")
        .takeIf { it.exitCode == 0 }
        ?.output
        ?.trim()
        ?.takeIf { it.isNotEmpty() }

    println("Rebooting Android device...")
    runAdbRootShellCommand("reboot")

    val deadlineNs = System.nanoTime() + TimeUnit.SECONDS.toNanos(timeoutSeconds)
    var lastStatus = "waiting for the device to reconnect"

    while (System.nanoTime() < deadlineNs) {
        val bootCompletedResult = runAdbShellCommand("getprop sys.boot_completed")
        if (bootCompletedResult.exitCode == 0) {
            val bootCompleted = bootCompletedResult.output.trim() == "1"
            val bootIdAfterReboot = runAdbShellCommand("cat $ANDROID_BOOT_ID_PATH")
                .takeIf { it.exitCode == 0 }
                ?.output
                ?.trim()
                ?.takeIf { it.isNotEmpty() }
            val bootIdChanged = bootIdBeforeReboot == null ||
                (bootIdAfterReboot != null && bootIdAfterReboot != bootIdBeforeReboot)

            if (bootCompleted && bootIdChanged) {
                println("Android device has finished booting.")
                wakeAndUnlockDevice()
                return
            }

            lastStatus = when {
                !bootIdChanged -> "ADB is online, but the device has not rebooted yet"
                !bootCompleted -> "ADB is online, waiting for Android boot completion"
                else -> "waiting for Android boot completion"
            }
        } else {
            lastStatus = bootCompletedResult.output.trim().ifEmpty { "device is offline" }
        }

        val remainingMs = TimeUnit.NANOSECONDS.toMillis(deadlineNs - System.nanoTime())
        if (remainingMs > 0) Thread.sleep(minOf(REBOOT_POLL_INTERVAL_MS, remainingMs))
    }

    error("Timed out after ${timeoutSeconds}s waiting for Android to boot. Last status: $lastStatus")
}

private fun wakeAndUnlockDevice() {
    var lastState = "unknown"

    repeat(WAKE_ATTEMPTS) { attempt ->
        if (attempt > 0) {
            println("Screen is still off (attempt ${attempt + 1}/$WAKE_ATTEMPTS), waking again...")
        }

        val wakeResult = runAdbRootShellCommand("input keyevent KEYCODE_WAKEUP")
        check(wakeResult.exitCode == 0) { "Failed to wake Android device: ${wakeResult.output.trim()}" }
        Thread.sleep(SCREEN_WAKE_WAIT_MS)

        val unlockResult = runAdbRootShellCommand("wm dismiss-keyguard")
        check(unlockResult.exitCode == 0) {
            "Failed to dismiss Android keyguard: ${unlockResult.output.trim()}"
        }
        Thread.sleep(KEYGUARD_DISMISS_WAIT_MS)

        // 退出码正常不代表屏幕真的亮了：必须回读电源/显示状态确认，否则会在黑屏上跑完整轮采样。
        val powerDump = runAdbShellCommand("dumpsys power").output
        val displayDump = runAdbShellCommand("dumpsys display").output
        if (isScreenOn(powerDump, displayDump)) {
            keepScreenOn()
            println("Android display is awake and the non-secure keyguard was dismissed.")
            return
        }
        lastState = screenStateSummary(powerDump, displayDump)
    }

    error(
        "Android screen did not turn on after $WAKE_ATTEMPTS wake-up attempts (last: $lastState). " +
            "Aborting instead of benchmarking a dark screen.",
    )
}

/**
 * 屏幕是否真的点亮：`mWakefulness=Awake`（power）与 `mScreenState=ON`（display）**两个来源都满足**才算亮。
 *
 * 只看 `input keyevent` 的退出码是不够的——命令成功但屏幕仍可能是灭的；也不能用 `dumpsys power` 里的
 * `Display Power:` 行，因为部分 ROM（含本机）并不打印它。
 */
internal fun isScreenOn(powerDump: String, displayDump: String): Boolean {
    val awake = powerDump.lineSequence().any { line ->
        val trimmed = line.trim()
        trimmed.startsWith("mWakefulness=") && trimmed.substringAfter('=').trim() == "Awake"
    }
    val displayOn = displayDump.lineSequence().any { line ->
        val trimmed = line.trim()
        trimmed.startsWith("mScreenState=") && trimmed.substringAfter('=').trim() == "ON"
    }
    return awake && displayOn
}

/** 失败信息里附带的简短状态：唤醒态、屏幕态、display suspend blocker 是否被持有。 */
internal fun screenStateSummary(powerDump: String, displayDump: String): String {
    fun pick(dump: String, prefix: String) = dump.lineSequence()
        .map { it.trim() }
        .firstOrNull { it.startsWith(prefix) }
        .orEmpty()

    return listOf(
        pick(powerDump, "mWakefulness="),
        pick(displayDump, "mScreenState="),
        pick(powerDump, "mHoldingDisplaySuspendBlocker="),
    ).filter { it.isNotEmpty() }.joinToString(", ").ifEmpty { "dumpsys reported no power/display state" }
}

/**
 * 把系统息屏超时设为 24 小时。
 *
 * `settings` 的值**跨重启持久**，所以每轮设一次是幂等的；仍以读回为准：写不进去或没生效就立刻失败，
 * 否则会变成"以为防了息屏、其实测试中途屏幕灭掉"的隐性错误。
 * 该设置由 shell 用户即可完成，不需要 root。
 */
private fun keepScreenOn() {
    val timeout = SCREEN_OFF_TIMEOUT_MS.toString()
    val put = runAdbShellCommand("settings put system screen_off_timeout $timeout")
    check(put.exitCode == 0) { "Failed to set screen_off_timeout: ${put.output.trim()}" }
    val readBack = runAdbShellCommand("settings get system screen_off_timeout").output.trim()
    check(readBack == timeout) {
        "screen_off_timeout did not take effect: expected $timeout, read back '$readBack'"
    }
    println("Screen off timeout set to 24h (screen_off_timeout=$readBack ms).")
}

fun restBeforeTest(waitMs: Long = PRE_TEST_REST_WAIT_MS) {
    require(waitMs >= 0) { "waitMs must not be negative, got $waitMs" }

    val startNs = System.nanoTime()
    println("Pre-test rest started: $waitMs ms (after swap setup, before the measured window).")
    Thread.sleep(waitMs)
    val elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startNs)
    println("Pre-test rest finished: elapsed=$elapsedMs ms.")
}
