package com.junj.device.swap

import com.junj.device.adb.AdbExecutor
import com.junj.device.adb.ProcessAdbExecutor
import com.junj.metrics.parser.parseZramBdStatResult
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * zRAM writeback 的后台节拍器：每 [intervalSec] 秒把 zram 已分配的页标记为 idle，再把 idle 页写回后端设备。
 *
 * 放在宿主侧而不是设备侧 `while+sleep` 脚本，是为了能随实验一起停（finally 里 cancelAndJoin）、
 * 每拍结果都能立刻看到；设备侧循环会在宿主崩溃后继续跑，且拿不到输出。
 *
 * 与内核的几条约定（见 admin-guide/blockdev/zram）：
 * - 需要 `CONFIG_ZRAM_WRITEBACK`（见 [requireZramWritebackSupport]）；
 * - `echo all > idle` 只是打标记，标记会保留到该页被再次访问；
 * - `echo idle > writeback` 是**同步**写回，上一次没写完时可能返回 -EAGAIN，这里只记录不重试，下一拍继续；
 * - 写回量同时会体现在 sample.csv 的 zramBdWrites / zramBdWriteBw 两列（采样列已换算为 KB）。
 */
class ZramWritebackJob(
    private val adb: AdbExecutor = ProcessAdbExecutor,
    private val intervalSec: Int,
    private val sysfs: String = ZRAM_SYSFS,
) {
    init {
        require(intervalSec > 0) { "writeback interval must be greater than 0, got $intervalSec" }
    }

    fun start(scope: CoroutineScope): Job = scope.launch(Dispatchers.IO) {
        try {
            println("Starting zRAM writeback job: every ${intervalSec}s mark idle + writeback idle pages")
            var tick = 0L
            while (isActive) {
                delay(intervalSec * 1_000L)

                tick++
                val kernelStart = adb.rootShell("cat /proc/uptime").output
                    .trim().substringBefore(' ').toDoubleOrNull()
                val marked = adb.rootShell("echo all > $sysfs/idle")
                // idle 标记失败时不下刷旧标记，避免把失败节拍误当成成功。
                val writtenBack = if (marked.exitCode == 0) {
                    // Toybox echo 可能只返回 1 而不打印 errno；dd 会明确报告 ENOSPC 等错误。
                    adb.rootShell("printf 'idle\\n' | dd of=$sysfs/writeback bs=5 count=1")
                } else null
                val bdStat = adb.rootShell("cat $sysfs/bd_stat").output.trim()

                println(
                    "[zram-writeback] tick=$tick markIdleExit=${marked.exitCode} " +
                        "writebackExit=${writtenBack?.exitCode ?: "SKIPPED"} ${formatZramBdStat(bdStat)}" +
                        if (marked.exitCode != 0 || writtenBack?.exitCode != 0) {
                            " message=${marked.output.trim()} ${writtenBack?.output.orEmpty().trim()}"
                        } else "",
                )
                if (marked.exitCode != 0 || writtenBack?.exitCode != 0) {
                    val diagnostics = adb.rootShell(
                        "for n in backing_dev writeback_limit_enable writeback_limit; do " +
                            "echo \"\$n:\"; cat $sysfs/\$n 2>&1; done; " +
                            "b=\$(cat $sysfs/backing_dev); n=\${b##*/}; " +
                            "case \"\$n\" in loop[0-9]*) " +
                            "f=\$(cat /sys/block/\$n/loop/backing_file); ls -lZ \"\$f\"; " +
                            "echo dio=\$(cat /sys/block/\$n/loop/dio); " +
                            "sectors=\$(cat /sys/block/\$n/size); " +
                            "echo backingCapacityKB=\$((sectors / 2));; esac; " +
                            "echo __RUSHHOUR_KERNEL_RECENT__; dmesg | tail -100",
                    )
                    val sections = diagnostics.output.split("__RUSHHOUR_KERNEL_RECENT__", limit = 2)
                    println("[zram-writeback] diagnostics exit=${diagnostics.exitCode}\n${sections[0].trim()}")
                    val freshKernel = filterFreshZramKernelMessages(sections.getOrElse(1) { "" }, kernelStart)
                    println("[zram-writeback] kernel messages since tick start:\n" +
                        freshKernel.ifBlank { "No matching fresh kernel messages captured" })
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}

/** tick 输出明确标注 4KB，避免与 SamplingItem 容量 KB 混淆。 */
internal fun formatZramBdStat(raw: String): String {
    val stat = parseZramBdStatResult(raw) ?: return "bdStatRaw(4KB)=$raw"
    return "bdCount(4KB)=${stat.bdCount} bdReads(4KB)=${stat.bdReads} bdWrites(4KB)=${stat.bdWrites} " +
        "backingUsedKB=${stat.bdCount * 4L}"
}

/** 不把之前独立测试的历史 AVC 当作本 tick 的错误。 */
internal fun filterFreshZramKernelMessages(raw: String, since: Double?): String {
    if (since == null) return "Kernel start timestamp unavailable; historical messages omitted"
    val timestamp = Regex("""^\[\s*(\d+(?:\.\d+)?)\]""")
    return raw.lineSequence().filter { line ->
        val time = timestamp.find(line)?.groupValues?.get(1)?.toDoubleOrNull()
        time != null && time >= since &&
            (line.contains("zram", ignoreCase = true) || line.contains("swap", ignoreCase = true))
    }.joinToString("\n")
}
