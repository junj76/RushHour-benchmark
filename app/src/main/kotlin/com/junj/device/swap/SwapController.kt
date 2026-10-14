package com.junj.device.swap

import com.junj.cli.ArgType
import com.junj.device.adb.runAdbRootShellCommand
import com.junj.output.logging.Logger
import com.junj.output.logging.LogType

/**
 * flash swap 文件路径（所有相关命令共用）。
 *
 * 注意：上游原本用 `/data/per_boot/flash.swap`，但当前测试机（华为 HBN-AL00 / EMUI）
 * 在这个目录下执行 mkswap 会让整机直接重启 —— 实测两次（一次 4GB 的自动跑、一次 256MB 的手动跑）
 * 都是 adb 掉线、手机重启、`/data/per_boot` 被清空。
 * 换成普通目录 `/data/local/tmp/` 后，dd → chmod → mkswap → swapon 全流程实测通过
 * （`/proc/swaps` 里能看到 file 类型的 swap）。
 */
const val FLASH_SWAP_FILE = "/data/local/tmp/flash.swap"

/**
 * 创建 flash swap 文件前，要求 /data 在 swap 文件之外至少还剩这么多空间（MB）。
 *
 * 把数据分区写满会让系统没有可写空间，轻则卡顿重则直接死机，
 * 所以要留出余量给系统自己的写入。
 */
private const val FREE_SPACE_MARGIN_MB = 512

fun disableZram() {
    runAdbRootShellCommand("swapoff /dev/block/zram0")
}

/**
 * 检查 /data 剩余空间是否够放 flash swap 文件（+ 余量），不够就直接报错中止。
 *
 * 背景：dd 写几 GB 的零到 /data 会把数据分区写满，系统随即卡死；
 * 之前 4GB 的配置在真机上就是这么把手机写死的。宁可提前失败，也不要写死设备。
 */
private fun requireEnoughDataSpace(flashSwapDeviceSizeMb: Int) {
    val dfResult = runAdbRootShellCommand("df -Pk /data")
    val availableKb = dfResult.output
        .lineSequence()
        .map { it.trim() }
        .filter { it.isNotEmpty() && !it.startsWith("Filesystem") }
        .lastOrNull()
        ?.split(Regex("""\s+"""))
        ?.getOrNull(3)
        ?.toLongOrNull()

    if (dfResult.exitCode != 0 || availableKb == null) {
        println(
            "警告：无法读取 /data 剩余空间（exit=${dfResult.exitCode}），跳过空间检查。" +
                "原始输出：${dfResult.output.trim().take(200)}"
        )
        return
    }

    val availableMb = availableKb / 1024
    val requiredMb = flashSwapDeviceSizeMb + FREE_SPACE_MARGIN_MB
    check(availableMb >= requiredMb) {
        "/data 剩余空间不足：可用 ${availableMb}MB，flash swap 需要 ${flashSwapDeviceSizeMb}MB" +
            "（另留 ${FREE_SPACE_MARGIN_MB}MB 余量）。请用 -s 减小 swap 文件，" +
            "或先清理 /data 后重试，否则可能把手机写死。"
    }

    println("/data 可用 ${availableMb}MB，flash swap 文件 ${flashSwapDeviceSizeMb}MB，空间检查通过。")
}

fun enableFlashSwap(flashSwapDeviceSizeMb: Int) {
    requireEnoughDataSpace(flashSwapDeviceSizeMb)

    runAdbRootShellCommand("dd if=/dev/zero of=$FLASH_SWAP_FILE bs=1M count=$flashSwapDeviceSizeMb")
    runAdbRootShellCommand("chmod 600 $FLASH_SWAP_FILE")
    runAdbRootShellCommand("mkswap $FLASH_SWAP_FILE")
    runAdbRootShellCommand("swapon $FLASH_SWAP_FILE")

    // mkswap/swapon 失败时 upstream 是不检查退出码的，整轮实验会悄悄跑成"没有 swap"，
    // 所以这里用 /proc/swaps 确认 swap 真的生效了，没生效就直接报错中止。
    val swaps = runAdbRootShellCommand("cat /proc/swaps")
    println(swaps.output)
    check(swaps.output.contains(FLASH_SWAP_FILE)) {
        "flash swap 没有生效：$FLASH_SWAP_FILE 不在 /proc/swaps 里。" +
            "请手动执行 dd / chmod / mkswap / swapon 排查（详见 CHANGES-windows-port.md 第七节）。"
    }
}

fun enableZswap() {
    runAdbRootShellCommand("echo Y > /sys/module/zswap/parameters/enabled")
    println("zSwap enabled: " + runAdbRootShellCommand("cat /sys/module/zswap/parameters/enabled").output)
    runAdbRootShellCommand("mount -t debugfs debugfs /sys/kernel/debug")
}

fun initSwapByType(type: Int, flashSwapDeviceSizeMb: Int, logger: Logger) {
        // 每轮开始：设采样率 → 清零并开启统计
    runAdbRootShellCommand("echo 30 > /sys/kernel/mm/swapin_latency/sample_rate")
    runAdbRootShellCommand("echo 1  > /sys/kernel/mm/swapin_latency/reset")
    runAdbRootShellCommand("echo 1  > /sys/kernel/mm/swapin_latency/enable")

    // 新增: 每轮开始调整cache level 
    runAdbRootShellCommand("echo 'cachelevel=7' > /sys/block/zram0/hyperhold_cache")
    when (type) {
        ArgType.NO_SWAP.code -> {
            logger.log(LogType.SUMMARY, "=== No Swap ===")
            disableZram()
        }
        ArgType.ONLY_ZRAM.code -> logger.log(LogType.SUMMARY, "=== Only zRAM ===")
        ArgType.ONLY_FLASH_SWAP.code -> {
            logger.log(LogType.SUMMARY, "=== Only Flash Swap ===")
            disableZram()
            enableFlashSwap(flashSwapDeviceSizeMb)
        }
        ArgType.ZSWAP.code -> {
            logger.log(LogType.SUMMARY, "=== ZSWAP ===")
            disableZram()
            enableFlashSwap(flashSwapDeviceSizeMb)
            enableZswap()
        }
    }
}
