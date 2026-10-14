package com.junj.device.simulator

import com.junj.device.adb.AdbExecutor
import com.junj.device.adb.CommandResult
import kotlin.test.Test
import kotlin.test.assertEquals
import java.nio.file.Paths

class TouchSimulatorTest {
    @Test
    fun `short video feed emits one swipe command per requested page`() {
        val adb = RecordingAdb()
        val simulator = TouchSimulator(adb)

        simulator.simulateShortVideoFeed(
            swipeCount = 3,
            intervalMs = 0,
            startX = 100,
            startY = 1_000,
            endX = 100,
            endY = 200,
            swipeDurationMs = 350,
        )

        assertEquals(
            listOf(
                "input swipe 100 1000 100 200 350",
                "input swipe 100 1000 100 200 350",
                "input swipe 100 1000 100 200 350",
            ),
            adb.rootCommands,
        )
    }

    @Test
    fun `app action command uses venv python and unified runner options`() {
        val actionsDirectory = Paths.get("/tmp/app_actions")
        val simulator = TouchSimulator(RecordingAdb(), actionsDirectory)
        val expectedPython = simulator.venvPythonPath().toString()

        // 解释器路径按平台而异（Windows: .venv\Scripts\python.exe，WSL/Linux: .venv/bin/python3），
        // 所以这里用 venvPythonPath() 作为期望值，只固定后面的统一参数。
        assertEquals(
            listOf(
                expectedPython,
                "run_app.py",
                "--time",
                "10",
                "--interval",
                "0.1",
                "--app",
                "bilibili",
            ),
            simulator.buildAppActionCommand("bilibili", expectedPython),
        )

        // 目录里没有 .venv 时不应该凭空认为解释器存在。
        assertEquals(null, simulator.locateVenvInterpreter())
    }

    private class RecordingAdb : AdbExecutor {
        val rootCommands = mutableListOf<String>()

        override fun shell(command: String): CommandResult = CommandResult(0, "")

        override fun rootShell(command: String): CommandResult {
            rootCommands += command
            return CommandResult(0, "")
        }
    }
}
