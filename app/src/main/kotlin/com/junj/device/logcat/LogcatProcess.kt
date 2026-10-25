package com.junj.device.logcat

import com.junj.device.adb.POWERSHELL_EXECUTABLE
import com.junj.device.adb.runAdbRootShellCommand
import java.io.File

/**
 * 杀进程事件（AOSP 的 LMKD / 内核 lowmemorykiller / 厂商自有内存管理）的采集与计数。
 *
 * 各平台把"杀了哪个进程"记在不同地方，所以这里同时抓两路：
 *   1) logcat：`main,system,crash`（AOSP 的 `lmkd`、厂商内存管理的 Android 侧日志）
 *      + `events`（框架的 `am_kill` 事件，AOSP 与 HarmonyOS 都有）
 *   2) 内核环形缓冲 `dmesg -w`（内嵌 lowmemorykiller / hisi_lmk 之类的 pr_info）
 *
 * 采集用**宽匹配**（宁可多留证据），计数用**窄匹配**（只数真正的"杀死某进程"事件，
 * 避免把日志里无关的 "kill" 计入）。华为/荣耀的自有标签未知，先用宽匹配把证据收下来，
 * 跑一轮后按实际 tag 收窄即可。
 *
 * 注意：正则里不能出现单引号/双引号字面量（它会被拼进 PowerShell 的单引号字符串），
 * 需要引号时用 `\x27` / `\x22`。
 */
const val LMK_CAPTURE_PATTERN: String =
    "(?i)lowmemorykiller|lmkd|am_kill|hisi_lmk|hwlmk|hilmk|memmgr|mem_mgr|hwmem|killing"

/**
 * **严格口径**：低内存触发的杀进程。三种可辨认的形状：
 *   - 内核 lowmemorykiller："lowmemorykiller: Killing 'com.x' (1234)"
 *   - 用户态 lmkd："lmkd: Killing 'com.x' (1234), uid …, oom_score_adj …"
 *   - 框架事件缓冲："am_kill: [0,10123,com.x,900,…]"
 * 以及厂商自有内存管理的标签（hisi_lmk/hwlmk/hilmk/memmgr/mem_mgr/hwmem）+ kill。
 */
const val LMK_COUNT_PATTERN: String =
    "(?i)am_kill|" +
        "killing\\s+[\\x27\\x22][\\w.]+|" +
        "(lmkd|lowmemorykiller|hilmk|hisi_lmk|hwlmk|memmgr|mem_mgr|hwmem).{0,60}kill"

/**
 * **宽口径**：框架记录的所有"杀进程"事件。本机（HBN-AL00）的格式是
 * `ActivityManager: Killing <pid>:<proc>/<uid> (adj N): <reason>`，
 * reason 里既有 `kill background`（正常清理后台）也可能是低内存触发，
 * 所以它只作为"被杀进程总数"的上下文，不并进 lmkdCnt。
 */
const val PROC_KILL_PATTERN: String =
    "(?i)activitymanager.*killing\\s+\\d+:|(lmkd|lowmemorykiller).{0,60}killing"

private val LMK_COUNT_REGEX = Regex(LMK_COUNT_PATTERN)
private val PROC_KILL_REGEX = Regex(PROC_KILL_PATTERN)

/**
 * 启动两路采集进程：返回值的第 0 项写 [logcatFile]，第 1 项写 [kernelFile]。
 * `dmesg -w` 不被支持时 kernel 文件为空，不影响其它统计。
 */
fun startLogcatProcesses(logcatFile: File, kernelFile: File): List<Process> {
    runAdbRootShellCommand("logcat -c")
    runAdbRootShellCommand("dmesg -C")

    // Windows 上没有 bash/grep，这里用 PowerShell：`Select-String -Pattern` 走 .NET 正则，
    // `ForEach-Object { $_.Line }` 只输出匹配到的整行并逐行写出（等价 --line-buffered）。
    val logcatScript =
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(\$false)\n" +
            "& adb.exe shell logcat -v threadtime -b main,system,events,crash | " +
            "Select-String -Pattern '$LMK_CAPTURE_PATTERN' | " +
            "ForEach-Object { \$_.Line }"

    val kernelScript =
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(\$false)\n" +
            "& adb.exe shell dmesg -w | " +
            "Select-String -Pattern '$LMK_CAPTURE_PATTERN' | " +
            "ForEach-Object { \$_.Line }"

    return listOf(
        startPowerShell(logcatScript, logcatFile),
        startPowerShell(kernelScript, kernelFile),
    )
}

private fun startPowerShell(script: String, output: File): Process =
    ProcessBuilder(
        POWERSHELL_EXECUTABLE,
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    )
        .redirectOutput(output)
        .redirectError(ProcessBuilder.Redirect.INHERIT)
        .start()

/**
 * 统计杀进程次数：按"杀进程事件"的窄匹配计数（不是数文件行数——同一次杀进程可能打多行）。
 * 两个来源（logcat / 内核缓冲）一起数。
 */
fun countLmkKills(vararg files: File): Int = countMatches(LMK_COUNT_REGEX, files)

/** 统计"被杀进程总数"（含系统正常清理后台），用于和 [countLmkKills] 对照。 */
fun countProcessKills(vararg files: File): Int = countMatches(PROC_KILL_REGEX, files)

private fun countMatches(regex: Regex, files: Array<out File>): Int =
    files.filter { it.isFile }.sumOf { file ->
        file.useLines { lines -> lines.count { regex.containsMatchIn(it) } }
    }
