package com.junj.device.simulator

import com.junj.device.adb.AdbExecutor
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

private const val ACTION_TIME_SECONDS = "10"
private const val ACTION_INTERVAL_SECONDS = "0.1"

class TouchSimulator(
    private val adb: AdbExecutor,
    private val actionsDirectory: Path = locateActionsDirectory(),
) {
    /**
     * Runs the configured Python UI scenario for [name].
     *
     * Python stdout and stderr are inherited by the benchmark process and are
     * therefore shown directly in the terminal. Apps without a profile are
     * skipped so that an unsupported app does not stop the benchmark.
     */
    fun simulate(name: String) {
        Thread.sleep(4_000)
        if (name in arrayOf("dianping", "jd", "meituan", "xiecheng", "qqmusic", "wechat", "jd"))
            return
        if (name in arrayOf("douyin", "kuaishou", "zhihu")) {
            simulateShortVideoFeed(3, 3_000)
            return
        }
        val profile = actionsDirectory.resolve("profiles").resolve("$name.json")
        if (!Files.isRegularFile(profile)) {
            println("[app-actions][$name] skipped: no profile found")
            return
        }

        val launcher = actionsDirectory.parent.resolve("wsl_run_app.sh")
        val runner = actionsDirectory.resolve("run_app.py")
        check(Files.isRegularFile(launcher)) {
            "Windows Python launcher is unavailable: $launcher"
        }
        check(Files.isRegularFile(runner)) {
            "App action runner is unavailable: $runner"
        }

        val command = buildAppActionCommand(name)
        println("[app-actions][$name] starting: ${command.joinToString(" ")}")

        val process = ProcessBuilder(command)
            .directory(actionsDirectory.toFile())
            .inheritIO()
            .start()

        val exitCode = process.waitFor()
        if (exitCode == 0) {
            println("[app-actions][$name] completed")
        } else {
            System.err.println(
                "[app-actions][$name] failed with exit code $exitCode"
            )
        }
    }

    internal fun buildAppActionCommand(name: String): List<String> = listOf(
        "bash",
        actionsDirectory.parent.resolve("wsl_run_app.sh").toString(),
        "--time",
        ACTION_TIME_SECONDS,
        "--interval",
        ACTION_INTERVAL_SECONDS,
        "--app",
        name,
    )

    fun simulateShortVideoFeed(
        swipeCount: Int,
        intervalMs: Long,
        startX: Int = 540,
        startY: Int = 1_600,
        endX: Int = 540,
        endY: Int = 400,
        swipeDurationMs: Long = 500L,
    ) {
        require(swipeCount >= 0) { "swipeCount must be non-negative" }
        require(intervalMs >= 0) { "intervalMs must be non-negative" }
        require(swipeDurationMs > 0) { "swipeDurationMs must be greater than 0" }

        repeat(swipeCount) { index ->
            val result = adb.rootShell(
                "input swipe $startX $startY $endX $endY $swipeDurationMs"
            )
            check(result.exitCode == 0) {
                "Failed to swipe short-video feed: ${result.output.trim()}"
            }

            if (index < swipeCount - 1 && intervalMs > 0) {
                Thread.sleep(intervalMs)
            }
        }
    }

    companion object {
        private fun locateActionsDirectory(): Path {
            val candidates = listOf(
                Paths.get("app_actions/ENapp"),
                Paths.get("../app_actions/ENapp"),
            )
            return candidates
                .map { it.toAbsolutePath().normalize() }
                .firstOrNull { Files.isRegularFile(it.resolve("run_app.py")) }
                ?: error(
                    "Cannot locate app_actions directory from " +
                        Paths.get("").toAbsolutePath().normalize()
                )
        }
    }
}
