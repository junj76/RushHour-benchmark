package com.junj.device.adb

import com.junj.output.logging.CommandDiagnostics

data class CommandResult(
    val exitCode: Int,
    val output: String
)

interface AdbExecutor {
    fun shell(command: String): CommandResult
    fun rootShell(command: String): CommandResult

    /** 探针类命令可以声明"失败是预期结果"（例如查询一个可能不存在的进程）。 */
    fun rootShell(command: String, expectedFailure: (CommandResult) -> Boolean): CommandResult =
        rootShell(command)
}

object ProcessAdbExecutor : AdbExecutor {
    override fun shell(command: String): CommandResult = runAdbShellCommand(command)
    override fun rootShell(command: String): CommandResult = runAdbRootShellCommand(command)
    override fun rootShell(command: String, expectedFailure: (CommandResult) -> Boolean): CommandResult =
        runAdbRootShellCommand(command, expectedFailure)
}

/**
 * 本机命令行解释器。
 *
 * 项目原来依赖 Linux/macOS 的 `/bin/bash`，Windows 上没有这个可执行文件，
 * 因此统一改用 Windows 自带的 PowerShell。命令本身仍然在设备端执行，
 * 只有“怎么把命令交给 adb.exe”这一层发生了变化。
 */
internal const val POWERSHELL_EXECUTABLE = "powershell.exe"

/**
 * 存放待执行命令的临时环境变量名。
 *
 * 命令原文只作为数据传递，不会被本机 PowerShell 当成脚本文本解析，
 * 这样命令里的 `2>/dev/null`、`>`、空格等都能原样到达设备端。
 */
private const val SHELL_COMMAND_ENV = "ADB_SHELL_COMMAND"
private const val ROOT_COMMAND_ENV = "ADB_ROOT_COMMAND"

/**
 * 设备端 root shell 的启动参数（换机型只改这一行）。
 *
 * 当前测试机是 eng 版固件，root 程序完整路径是 `/eng/system/xbin/su`，
 * 用法是 `su <uid> <命令>`，并不支持 `su -c <命令>`：
 *   - `adb shell su -c id`        → 报错
 *   - `/eng/system/xbin/su 0 id`  → 以 root 执行 `id`（可用）
 * 因此这里用 `/eng/system/xbin/su 0 sh` 起一个 root 身份的 sh，命令原文再从 stdin 喂给它。
 *
 * 如果是 Magisk 这类支持 `-c` 的机型，把它改成 "shell su -c sh" 即可。
 */
private const val ROOT_SHELL_DEVICE_COMMAND = "shell /eng/system/xbin/su 0 sh"

/**
 * 让 PowerShell 用 UTF-8 写自己的 stdout。
 *
 * 不设置的话，中文 Windows 上会跟随 OEM 代码页（936），
 * 经 PowerShell 转发的命令输出到 Kotlin 侧就可能变成乱码。
 */
private const val UTF8_CONSOLE_ENCODING =
    "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(\$false)"

/** 把最后一条本机命令（adb.exe）的退出码透传给 Kotlin；adb 本身都启动不了时按失败处理。 */
private const val EXIT_WITH_LAST_EXIT_CODE =
    "if (\$null -eq \$LASTEXITCODE) { exit 1 } else { exit \$LASTEXITCODE }"

/** 通用脚本收尾：优先透传本机命令的退出码，否则按 PowerShell 自身的成功/失败状态返回。 */
private const val EXIT_WITH_STATUS =
    "\$succeeded = \$?\n" +
        "\$code = \$LASTEXITCODE\n" +
        "if (\$null -ne \$code) { exit \$code }\n" +
        "if (\$succeeded) { exit 0 } else { exit 1 }"

/** 执行本机 PowerShell 命令（原来的 runBashCommand）。 */
fun runPowerShellCommand(command: String): CommandResult =
    runPowerShellScript("$command\n$EXIT_WITH_STATUS")

/**
 * 执行 `adb shell <command>`。
 *
 * 命令通过环境变量传入，PowerShell 只负责按空白拆词后交给 `adb.exe`
 * （`-split` 复现旧版 `adb.exe shell $command` 的拆词行为），
 * 设备端仍然由 Android 的 sh 解释这条命令。
 */
fun runAdbShellCommand(command: String): CommandResult {
    val result = runPowerShellScript(
        "$UTF8_CONSOLE_ENCODING\n" +
            "& adb.exe shell (-split \$env:$SHELL_COMMAND_ENV)\n" +
            EXIT_WITH_LAST_EXIT_CODE,
        mapOf(SHELL_COMMAND_ENV to command),
    )
    CommandDiagnostics.recordCommandProblem(command, result.exitCode, result.output)
    return result
}

/**
 * 以 root 身份在设备上执行命令（见 [ROOT_SHELL_DEVICE_COMMAND]）。
 *
 * 命令原文以 UTF-8 写进 adb 的 stdin（只补一个 LF，不带 CR），由设备端的 root sh 读取执行，
 * 对应原来的 `printf '%s\n' "$ADB_ROOT_COMMAND" | adb.exe shell su -c sh`。
 *
 * 这里不能用 PowerShell 管道（`$env:X | adb.exe ...`）：管道给子进程 stdin 会自动补 CRLF，
 * 设备端 sh 会把 `\r` 当成最后一个参数的一部分（`logcat -c\r` 直接报错）。
 * 所以改用 .NET 的 Process 精确写入“命令 + 单个 LF”。
 *
 * @param expectedFailure 探针类命令可以声明"失败是预期结果"，此时不会记入 command.log。
 */
fun runAdbRootShellCommand(
    command: String,
    expectedFailure: (CommandResult) -> Boolean = { false },
): CommandResult {
    val result = runPowerShellScript(
        listOf(
            "\$ErrorActionPreference = 'Stop'",
            UTF8_CONSOLE_ENCODING,
            "\$psi = [System.Diagnostics.ProcessStartInfo]::new('adb.exe', '$ROOT_SHELL_DEVICE_COMMAND')",
            "\$psi.UseShellExecute = \$false",
            "\$psi.RedirectStandardInput = \$true",
            "\$process = [System.Diagnostics.Process]::Start(\$psi)",
            "\$bytes = [System.Text.UTF8Encoding]::new(\$false).GetBytes(\$env:$ROOT_COMMAND_ENV + [char]10)",
            "\$process.StandardInput.BaseStream.Write(\$bytes, 0, \$bytes.Length)",
            "\$process.StandardInput.BaseStream.Flush()",
            "\$process.StandardInput.Close()",
            "\$process.WaitForExit()",
            "exit \$process.ExitCode",
        ).joinToString("\n"),
        mapOf(ROOT_COMMAND_ENV to command),
    )
    if (!expectedFailure(result)) {
        CommandDiagnostics.recordCommandProblem(command, result.exitCode, result.output)
    }
    return result
}

private fun runPowerShellScript(
    script: String,
    environment: Map<String, String> = emptyMap(),
): CommandResult {
    val processBuilder = ProcessBuilder(
        POWERSHELL_EXECUTABLE,
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    )
        .redirectErrorStream(true)

    processBuilder.environment().putAll(environment)

    val process = processBuilder.start()

    val output = process.inputStream
        .bufferedReader(Charsets.UTF_8)
        .use { it.readText() }
    val exitCode = process.waitFor()

    return CommandResult(exitCode, output)
}
