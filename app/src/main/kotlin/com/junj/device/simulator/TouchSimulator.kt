package com.junj.device.simulator

import com.junj.device.adb.AdbExecutor
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

private const val ACTION_TIME_SECONDS = "10"
private const val ACTION_INTERVAL_SECONDS = "0.1"
private const val ACTION_WAIT_MS = 4_000L

/** Python 侧调用 Windows Android Platform Tools 时用的 adb 可执行文件名。 */
private const val WINDOWS_ADB_EXECUTABLE = "adb.exe"

/** 允许用环境变量指定解释器，例如 BENCH_PYTHON=C:\Python312\python.exe。 */
private const val PYTHON_OVERRIDE_ENV = "BENCH_PYTHON"

/** 有 profile 也不需要跑 Python 动作的 App（触控动作对它们没有意义）。 */
private val APPS_WITHOUT_ACTIONS = arrayOf(
    "dianping", "jd", "meituan", "xiecheng", "qqmusic", "weixin", "jd",
)

/** 用 adb `input swipe` 直接模拟短视频上滑，不需要 Python。 */
private val SHORT_VIDEO_APPS = arrayOf("douyin", "kuaishou", "zhihu")

/**
 * 虚拟环境里的 Python 解释器路径，按平台优先：
 *   - Windows venv：`.venv\Scripts\python.exe`
 *   - WSL / Linux venv：`.venv/bin/python3`（少数发行版是 `.venv/bin/python`）
 */
private val VENV_PYTHON_CANDIDATES = listOf(
    ".venv/Scripts/python.exe",
    ".venv/bin/python3",
    ".venv/bin/python",
)

private val IS_WINDOWS: Boolean =
    System.getProperty("os.name").orEmpty().startsWith("Windows", ignoreCase = true)

class TouchSimulator(
    private val adb: AdbExecutor,
    private val actionsDirectory: Path = locateActionsDirectory(),
) {
    /**
     * Runs the configured Python UI scenario for [name].
     *
     * Python stdout and stderr are inherited by the benchmark process and are
     * therefore shown directly in the terminal. Apps without a profile, or runs
     * without a usable Python interpreter, are skipped so that an unsupported
     * app (or a missing virtual environment) does not stop the benchmark.
     */
    fun simulate(name: String) {
        Thread.sleep(ACTION_WAIT_MS)
        if (name in APPS_WITHOUT_ACTIONS) return
        if (name in SHORT_VIDEO_APPS) {
            simulateShortVideoFeed(3, 3_000)
            return
        }

        val profile = actionsDirectory.resolve("profiles").resolve("$name.json")
        if (!Files.isRegularFile(profile)) {
            println("[app-actions][$name] skipped: no profile found")
            return
        }

        val runner = actionsDirectory.resolve("run_app.py")
        if (!Files.isRegularFile(runner)) {
            println("[app-actions][$name] skipped: run_app.py not found in $actionsDirectory")
            return
        }

        val interpreter = resolvePythonInterpreter()
        val command = buildAppActionCommand(name, interpreter)
        println("[app-actions][$name] starting: ${command.joinToString(" ")}")

        val process = try {
            ProcessBuilder(command)
                .directory(actionsDirectory.toFile())
                .inheritIO()
                .apply {
                    environment()["ADBUTILS_ADB_PATH"] = WINDOWS_ADB_EXECUTABLE
                    environment()["PYTHONUNBUFFERED"] = "1"
                }
                .start()
        } catch (e: Exception) {
            // 找不到解释器或启动失败时只跳过这个 App，不要中断整轮 benchmark。
            println("[app-actions][$name] skipped: cannot start ${interpreter}. ${e.message}")
            println(
                "[app-actions] 提示：在 app_actions 下创建虚拟环境并安装依赖 —— " +
                    "Windows: py -3 -m venv .venv; .venv\\Scripts\\python.exe -m pip install -r requirements.txt ｜ " +
                    "WSL/Linux: python3 -m venv .venv; .venv/bin/python3 -m pip install -r requirements.txt"
            )
            return
        }

        val exitCode = process.waitFor()
        if (exitCode == 0) {
            println("[app-actions][$name] completed")
        } else {
            System.err.println(
                "[app-actions][$name] failed with exit code $exitCode"
            )
        }
    }

    /**
     * 解析要用的 Python 解释器：
     *   1. 环境变量 [PYTHON_OVERRIDE_ENV] 指定的路径；
     *   2. 虚拟环境 `app_actions/.venv` 里的解释器（按平台优先 Windows/WSL 布局）；
     *   3. 退回 PATH 上的 `python.exe`（Windows）或 `python3`（其它平台）。
     *
     * 返回值可能是「绝对路径」或「命令名」，交给 ProcessBuilder 解析。
     */
    internal fun resolvePythonInterpreter(): String =
        System.getenv(PYTHON_OVERRIDE_ENV)?.takeIf { it.isNotBlank() }
            ?: locateVenvInterpreter()?.toString()
            ?: if (IS_WINDOWS) "python.exe" else "python3"

    /** 按平台顺序在 .venv 里找解释器，找不到返回 null。 */
    internal fun locateVenvInterpreter(): Path? {
        // 允许两种放法：app_actions/.venv（README 的布局）和仓库根目录下的 .venv。
        val roots = listOfNotNull(actionsDirectory, actionsDirectory.parent)
        return roots
            .flatMap { root -> VENV_PYTHON_CANDIDATES.map { root.resolve(it) } }
            .firstOrNull { Files.isRegularFile(it) }
    }

    /** 当前平台「期望」的 venv 解释器路径（不检查是否存在），供测试与日志使用。 */
    internal fun venvPythonPath(): Path =
        actionsDirectory.resolve(if (IS_WINDOWS) VENV_PYTHON_CANDIDATES[0] else VENV_PYTHON_CANDIDATES[1])

    internal fun buildAppActionCommand(
        name: String,
        interpreter: String = resolvePythonInterpreter(),
    ): List<String> = listOf(
        interpreter,
        "run_app.py",
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
                Paths.get("app_actions"),
                Paths.get("../app_actions"),
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
