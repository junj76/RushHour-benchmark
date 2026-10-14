package com.junj.device.lifecycle

import com.junj.device.adb.AdbExecutor
import com.junj.device.adb.ProcessAdbExecutor
import com.junj.device.adb.runAdbRootShellCommand
import com.junj.device.adb.runAdbShellCommand
import java.util.concurrent.TimeUnit

private const val DEFAULT_REBOOT_TIMEOUT_SECONDS = 300L
private const val REBOOT_POLL_INTERVAL_MS = 1_000L
private const val SCREEN_WAKE_WAIT_MS = 1_000L
private const val KEYGUARD_DISMISS_WAIT_MS = 1_000L
private const val POST_BOOT_STABILIZATION_WAIT_MS = 60_000L
private const val ANDROID_BOOT_ID_PATH = "/proc/sys/kernel/random/boot_id"

/** Reboots the connected Android device and waits for Android boot completion. */
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
                check(wakeAndUnlockDevice(ProcessAdbExecutor)) {
                    "Failed to wake and unlock the Android device after reboot."
                }
                stabilizeAfterBoot()
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

/**
 * 唤醒屏幕并解除"非安全"锁屏。
 *
 * 这一步很关键：设备息屏后，`am start -W` 的测量结果不再可信，
 * 而 app_actions 的 Python 脚本会直接以 `Screen is off; unlock and open the app home first`
 * 失败退出（表现为"手机一直没反应"）。所以测试开始前、以及每次启动 App 之前都要调用它。
 *
 * 失败只返回 false（由调用方决定是否告警），不会抛异常中断整轮测试。
 */
fun wakeAndUnlockDevice(adb: AdbExecutor): Boolean {
    val wakeResult = adb.rootShell("input keyevent KEYCODE_WAKEUP")
    if (wakeResult.exitCode != 0) {
        println("[device] 唤醒屏幕失败：${wakeResult.output.trim()}")
        return false
    }
    Thread.sleep(SCREEN_WAKE_WAIT_MS)

    val unlockResult = adb.rootShell("wm dismiss-keyguard")
    if (unlockResult.exitCode != 0) {
        println("[device] 解除锁屏失败：${unlockResult.output.trim()}")
        return false
    }
    Thread.sleep(KEYGUARD_DISMISS_WAIT_MS)
    return true
}

/** 测试期间保持屏幕常亮（`svc power stayon true`，接电源时生效），避免中途息屏。 */
fun enableStayAwake(adb: AdbExecutor = ProcessAdbExecutor): Boolean {
    val result = adb.rootShell("svc power stayon true")
    if (result.exitCode == 0) {
        println("[device] 已开启屏幕常亮（svc power stayon true）。")
        return true
    }
    println("[device] 开启屏幕常亮失败（可忽略）：${result.output.trim()}")
    return false
}

/** 恢复系统的自动息屏行为。 */
fun disableStayAwake(adb: AdbExecutor = ProcessAdbExecutor) {
    adb.rootShell("svc power stayon false")
}

private fun stabilizeAfterBoot() {
    println("Starting post-boot stabilization wait: $POST_BOOT_STABILIZATION_WAIT_MS ms.")
    val waitStartNs = System.nanoTime()
    Thread.sleep(POST_BOOT_STABILIZATION_WAIT_MS)
    val elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - waitStartNs)
    println("Post-boot stabilization wait finished: elapsed=${elapsedMs} ms.")
}
