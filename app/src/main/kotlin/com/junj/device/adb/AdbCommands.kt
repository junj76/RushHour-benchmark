package com.junj.device.adb

data class CommandResult(
    val exitCode: Int,
    val output: String
)

interface AdbExecutor {
    fun shell(command: String): CommandResult
    fun rootShell(command: String): CommandResult
    fun rootShell(command: String, expectedFailure: (CommandResult) -> Boolean): CommandResult = rootShell(command)
}

object ProcessAdbExecutor : AdbExecutor {
    override fun shell(command: String): CommandResult = runAdbShellCommand(command)
    override fun rootShell(command: String): CommandResult = runAdbRootShellCommand(command)
    override fun rootShell(command: String, expectedFailure: (CommandResult) -> Boolean): CommandResult =
        runAdbRootShellCommand(command, expectedFailure)
}

fun runBashCommand(command: String): CommandResult {
    val process = ProcessBuilder(
        "/bin/bash",
        "-lc",
        command
    )
        .redirectErrorStream(true)
        .start()

    val output = process.inputStream
        .bufferedReader(Charsets.UTF_8)
        .use { it.readText() }
    val exitCode = process.waitFor()
    
    return CommandResult(exitCode, output)
}

fun runAdbShellCommand(command: String) : CommandResult {
    val process = ProcessBuilder(
        "/bin/bash",
        "-lc",
        "adb.exe shell $command"
    )
        .redirectErrorStream(true)
        .start()
    
    val output = process.inputStream
        .bufferedReader(Charsets.UTF_8)
        .use { it.readText() }
    val exitCode = process.waitFor()
    
    return CommandResult(exitCode, output)
}

/**
 * 以 root 在设备上执行脚本（脚本经 stdin 交给 `su -c sh`）。
 *
 * 注意不要写成裸 `su`：Magisk 的 su 常常**不在 shell 的 PATH 里**
 * （典型位置是 `/debug_ramdisk/su`，它在 magic mount 生效前就已存在，开机早期也能用），
 * 裸 `su` 会得到 `su: inaccessible or not found`，于是所有 root 操作静默失败。
 * 这里先在设备上挑一个存在的 su，再 `exec` 它——此时 stdin 还没被读过，脚本仍会完整交给 `sh`。
 */
fun runAdbRootShellCommand(
    command: String,
    expectedFailure: (CommandResult) -> Boolean = { false },
): CommandResult {
    val hostScript =
        "printf '%s\\n' \"\$ADB_ROOT_COMMAND\" | " +
            "adb.exe shell 'SU=/debug_ramdisk/su; " +
            "[ -x \$SU ] || SU=/system/bin/su; " +
            "[ -x \$SU ] || SU=/system/xbin/su; " +
            "[ -x \$SU ] || SU=/sbin/su; " +
            "[ -x \$SU ] || SU=su; " +
            "exec \$SU -c sh'"

    val processBuilder = ProcessBuilder(
        "/bin/bash",
        "-c",
        hostScript,
    )
        .redirectErrorStream(true)

    processBuilder.environment()["ADB_ROOT_COMMAND"] = command

    val process = processBuilder.start()

    val output = process.inputStream
        .bufferedReader(Charsets.UTF_8)
        .use { it.readText() }

    val exitCode = process.waitFor()

    val result = CommandResult(exitCode, output)
    // Probes may expect an absent process; transport and permission errors still get reported.
    if (exitCode != 0 && !expectedFailure(result)) {
        println("[adb] root command failed (exit=$exitCode): $command")
        output.trim().takeIf { it.isNotEmpty() }?.let { println(it) }
    }

    return result
}
