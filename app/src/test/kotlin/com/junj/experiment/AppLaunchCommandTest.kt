package com.junj.experiment

import kotlin.test.Test
import kotlin.test.assertEquals
import org.junit.jupiter.api.condition.EnabledOnOs
import org.junit.jupiter.api.condition.OS

// 该用例用 /bin/sh 模拟 adb 与手机 shell 的引号传递，只在 POSIX 主机上可运行。
@EnabledOnOs(OS.LINUX, OS.MAC)
class AppLaunchCommandTest {
    @Test
    fun `component survives host and device shells without variable expansion`() {
        for (component in listOf(
            "com.google.android.youtube/.app.honeycomb.Shell\$HomeActivity",
            "org.wikipedia/.DefaultIcon",
        )) {
            // 用本地 sh 模拟 adb 接收命令后交给手机 Shell，不连接手机。
            val script = """
                adb.exe() {
                    shift
                    /bin/sh -c 'am() { printf "%s\n" "${'$'}@"; }; '"${'$'}*"
                }
                adb.exe shell ${buildAppLaunchCommand(component)}
            """.trimIndent()
            val builder = ProcessBuilder("/bin/bash", "-c", script).redirectErrorStream(true)
            builder.environment()["HomeActivity"] = "WRONG_ACTIVITY"
            val process = builder.start()
            val output = process.inputStream.bufferedReader().readText()
            assertEquals(0, process.waitFor(), output)
            assertEquals(listOf("start", "-W", "-n", component), output.trimEnd().lines())
        }
    }
}
