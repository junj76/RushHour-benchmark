package com.junj.experiment

import com.junj.config.ExperimentConfig
import com.junj.device.adb.AdbExecutor
import com.junj.device.lifecycle.wakeAndUnlockDevice
import com.junj.device.pid.getApplicationPid
import com.junj.device.pid.isApplicationProcessAlive
import com.junj.device.pid.waitForApplicationPid
import com.junj.device.simulator.TouchSimulator
import com.junj.domain.ExperimentResults
import com.junj.domain.TestClock
import com.junj.domain.app.ApplicationInfo
import com.junj.domain.launch.LaunchApplicationItem
import com.junj.domain.survival.AppSurvivalResult
import com.junj.metrics.parser.CommandType
import com.junj.metrics.parser.ResultField
import com.junj.metrics.parser.regexFindField
import com.junj.output.logging.CommandDiagnostics
import com.junj.output.logging.LogType
import com.junj.output.logging.Logger
import java.lang.Thread.sleep

class ExperimentRunner(
    private val adb: AdbExecutor,
    private val apps: List<ApplicationInfo>,
    private val results: ExperimentResults,
    private val logger: Logger,
    private val config: ExperimentConfig,
    private val clock: TestClock,
) {
    private data class LaunchedAppProcess(
        val launchPosition: Int,
        val app: ApplicationInfo,
        val launchedPid: Long?,
    )

    fun runTestRound(round: Int) {
        val touchSimulator = TouchSimulator(adb)
        val launchedProcesses = ArrayList<LaunchedAppProcess>()
        for ((index, app) in apps.withIndex()) {
            // 息屏后 am start -W 的测量与 app_actions 的 UI 动作都会失效，所以每次启动前先唤醒并解锁
            wakeAndUnlockDevice(adb)
            val launchStartNs = System.nanoTime()
            val launchStamp = clock.elapsedMs()
            val nextLaunchNs = launchStartNs + config.launchIntervalMs * 1_000_000L
            adb.rootShell("dumpsys gfxinfo ${app.packageName} reset")
            val amStartResult = adb.shell("am start -W -n ${app.componentName}")
            if (regexFindField(CommandType.AM_START, ResultField.LAUNCH_STATE, amStartResult.output) == null) {
                // 没回 LaunchState 基本就是应用没装、或组件名和这台机器对不上，把原始输出留档。
                CommandDiagnostics.record(
                    "am-start/no-launch-state",
                    "am start -W -n ${app.componentName}",
                    amStartResult.output,
                )
            }
            val launchedPid = waitForApplicationPid(adb, app.packageName)
            touchSimulator.simulate(app.name)
            sleepUntil(launchStartNs + config.collectDelayMs * 1_000_000L)
            val gfxinfo = adb.shell("dumpsys gfxinfo ${app.packageName}")
            val meminfo = adb.shell("dumpsys meminfo ${app.packageName}")

            val result = LaunchApplicationItem(
                launchStamp = launchStamp,
                amStartRound = round,
                amStartAppName = app.name,
                amStartLaunchState = regexFindField(CommandType.AM_START, ResultField.LAUNCH_STATE, amStartResult.output) ?: "",
                amStartTotalTime = regexFindField(CommandType.AM_START, ResultField.TOTAL_TIME, amStartResult.output)?.toLongOrNull() ?: 0,
                amStartWaitTime = regexFindField(CommandType.AM_START, ResultField.WAIT_TIME, amStartResult.output)?.toLongOrNull() ?: 0,
                amStartStatus = regexFindField(CommandType.AM_START, ResultField.STATUS, amStartResult.output) ?: "",
                dumpsysGfxInfoJankyFrames = regexFindField(CommandType.DUMPSYS_GFXINFO, ResultField.JANKY_FRAMES_PCT, gfxinfo.output)?.toDoubleOrNull() ?: 0.0,
                dumpsysGfxInfoP50RenderLat = regexFindField(CommandType.DUMPSYS_GFXINFO, ResultField.P50_RENDER_LAT, gfxinfo.output)?.toIntOrNull() ?: 0,
                dumpsysGfxInfoP90RenderLat = regexFindField(CommandType.DUMPSYS_GFXINFO, ResultField.P90_RENDER_LAT, gfxinfo.output)?.toIntOrNull() ?: 0,
                dumpsysGfxInfoP95RenderLat = regexFindField(CommandType.DUMPSYS_GFXINFO, ResultField.P95_RENDER_LAT, gfxinfo.output)?.toIntOrNull() ?: 0,
                dumpsysGfxInfoP99RenderLat = regexFindField(CommandType.DUMPSYS_GFXINFO, ResultField.P99_RENDER_LAT, gfxinfo.output)?.toIntOrNull() ?: 0,
                dumpsysMemInfoTotalPss = regexFindField(CommandType.DUMPSYS_MEMINFO, ResultField.TOTAL_PSS, meminfo.output)?.toIntOrNull() ?: 0,
            )
            results.launches += result
            launchedProcesses += LaunchedAppProcess(
                launchPosition = index + 1,
                app = app,
                launchedPid = launchedPid,
            )
            logger.log(LogType.LAUNCH, result)
            sleepUntil(nextLaunchNs)
        }

        val roundSurvivals = launchedProcesses.map { launched ->
            val pidAtRoundEnd = getApplicationPid(adb, launched.app.packageName)
            val originalProcessAlive = isApplicationProcessAlive(
                adb = adb,
                packageName = launched.app.packageName,
                pid = launched.launchedPid,
            )

            AppSurvivalResult(
                round = round,
                launchPosition = launched.launchPosition,
                appName = launched.app.name,
                packageName = launched.app.packageName,
                launchedPid = launched.launchedPid,
                pidAtRoundEnd = pidAtRoundEnd,
                originalProcessAlive = originalProcessAlive,
                appCurrentlyRunning = pidAtRoundEnd != null,
            )
        }
        results.survivals += roundSurvivals
        roundSurvivals.forEach { logger.log(LogType.LAUNCH, it) }

        val aliveApps = roundSurvivals.filter { it.originalProcessAlive }
        val aliveRatio = if (roundSurvivals.isEmpty()) {
            0.0
        } else {
            aliveApps.size.toDouble() / roundSurvivals.size
        }
        logger.log(
            LogType.LAUNCH,
            "round=$round, launchCnt=${roundSurvivals.size}, " +
                "aliveCount=${aliveApps.size}, aliveAppRatio=${"%.2f".format(aliveRatio * 100)}%, " +
                "aliveAppList=${aliveApps.map { it.appName }}",
        )
    }

    private fun sleepUntil(deadlineNs: Long) {
        while (true) {
            val remainingNs = deadlineNs - System.nanoTime()
            if (remainingNs <= 0) return
            sleep(remainingNs / 1_000_000L, (remainingNs % 1_000_000L).toInt())
        }
    }
}
