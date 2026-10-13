package com.junj.device.lifecycle

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
    val wakeResult = runAdbRootShellCommand("input keyevent KEYCODE_WAKEUP")
    check(wakeResult.exitCode == 0) { "Failed to wake Android device: ${wakeResult.output.trim()}" }
    Thread.sleep(SCREEN_WAKE_WAIT_MS)

    val unlockResult = runAdbRootShellCommand("wm dismiss-keyguard")
    check(unlockResult.exitCode == 0) {
        "Failed to dismiss Android keyguard: ${unlockResult.output.trim()}"
    }
    Thread.sleep(KEYGUARD_DISMISS_WAIT_MS)
    println("Android display is awake and the non-secure keyguard was dismissed.")

    val waitStartNs = System.nanoTime()
    println("Starting post-boot stabilization wait: $POST_BOOT_STABILIZATION_WAIT_MS ms.")
    Thread.sleep(POST_BOOT_STABILIZATION_WAIT_MS)
    val elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - waitStartNs)
    println("Post-boot stabilization wait finished: elapsed=${elapsedMs} ms.")
}
