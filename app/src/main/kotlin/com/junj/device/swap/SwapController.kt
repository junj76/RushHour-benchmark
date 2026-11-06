package com.junj.device.swap

import com.junj.cli.ArgType
import com.junj.config.DEFAULT_ZSWAP_MAX_POOL_PERCENT
import com.junj.config.ExperimentConfig
import com.junj.device.adb.AdbExecutor
import com.junj.device.adb.runAdbRootShellCommand
import com.junj.output.logging.Logger
import com.junj.output.logging.LogType

internal const val FLASH_SWAP_FILE = "/data/per_boot/flash.swap"
internal const val COMPRESSION_ALGORITHM = "lz4"
internal data class SwapConfigProbe(val label: String, val command: String)

class SwapController(
    val adb: AdbExecutor,
    val logger: Logger,
    val config: ExperimentConfig,
) {
    fun enableZram(algorithmName: String = COMPRESSION_ALGORITHM) {
        val disksize = adb.rootShell("cat $ZRAM_SYSFS/disksize").output.trim()
        check(disksize.isNotEmpty() && disksize.all { it.isDigit() } && disksize != "0") {
            "Refusing to reconfigure zRAM: failed to read the current disksize (got '$disksize'). " +
                "A value of 0 means the device was left reset; reboot so init can rebuild it."
        }

        adb.rootShell("swapoff $ZRAM_DEVICE")
        adb.rootShell("echo 1 > $ZRAM_SYSFS/reset")
        // Must be written after reset and before disksize; the kernel refuses it on an active device.
        adb.rootShell("echo $algorithmName > $ZRAM_SYSFS/comp_algorithm")
        adb.rootShell("echo $disksize > $ZRAM_SYSFS/disksize")
        adb.rootShell("mkswap $ZRAM_DEVICE")
        adb.rootShell("swapon $ZRAM_DEVICE")

        val readBack = adb.rootShell("cat $ZRAM_SYSFS/comp_algorithm").output.trim()
        check(readBack.contains("[$algorithmName]")) {
            "zRAM compression algorithm is not '$algorithmName' after setup: $readBack"
        }
        println("zRAM configured: algorithm=$algorithmName, disksize=$disksize")
        println(adb.rootShell("cat /proc/swaps").output)
    }

    fun disableZram() {
        runAdbRootShellCommand("swapoff /dev/block/zram0")
    }

    fun enableFlashSwap(flashSwapDeviceSizeMB: Int) {
        val device = mapFlashDevice(adb, flashSwapDeviceSizeMB)
        checkedZramCommand(adb, "mkswap $device")
        checkedZramCommand(adb, "swapon $device")
        println(adb.rootShell("cat /proc/swaps").output)
    }

    /**
     * Enables zswap with [algorithmName] as compressor and [maxPoolPercent] as the pool cap, using [zpool] for compressed memory.
     *
     * `max_pool_percent` decides whether zswap ever spills to the flash swap: with a large pool the
     * pages stay compressed in RAM and nothing is written back (written_back_pages stays 0); with a
     * small pool accept_threshold_percent rejects pages, which are then written straight to the
     * swap file. All settings are read back so a rejected write is reported, not silently ignored.
     */
    fun enableZswap(
        algorithmName: String = COMPRESSION_ALGORITHM,
        maxPoolPercent: Int = DEFAULT_ZSWAP_MAX_POOL_PERCENT,
        zpool: String = "zsmalloc",
    ) {
        require(zpool in setOf("zsmalloc", "zbud")) { "Unsupported zswap zpool: $zpool" }
        require(maxPoolPercent in 1..100) {
            "max_pool_percent must be between 1 and 100, got $maxPoolPercent"
        }

        val poolLimit = adb.rootShell("echo $maxPoolPercent > /sys/module/zswap/parameters/max_pool_percent")
        check(poolLimit.exitCode == 0) {
            "Failed to set zswap max_pool_percent to $maxPoolPercent: ${poolLimit.output.trim()}"
        }

        val applied = adb.rootShell("echo $algorithmName > /sys/module/zswap/parameters/compressor")
        check(applied.exitCode == 0) {
            "Failed to set the zswap compressor to '$algorithmName': ${applied.output.trim()}"
        }
        val poolApplied = adb.rootShell("echo $zpool > /sys/module/zswap/parameters/zpool")
        check(poolApplied.exitCode == 0) {
            "Failed to set the zswap zpool to '$zpool': ${poolApplied.output.trim()}"
        }
        val zpoolReadBack = adb.rootShell("cat /sys/module/zswap/parameters/zpool").output.trim()
        check(zpoolReadBack == zpool) {
            "zswap zpool did not take effect: expected '$zpool', read back '$zpoolReadBack'"
        }
        adb.rootShell("echo Y > /sys/module/zswap/parameters/enabled")

        val compressorReadBack = adb.rootShell("cat /sys/module/zswap/parameters/compressor").output.trim()
        check(compressorReadBack == algorithmName) {
            "zswap compressor did not take effect: expected '$algorithmName', read back '$compressorReadBack'"
        }
        val poolReadBack = adb.rootShell("cat /sys/module/zswap/parameters/max_pool_percent").output.trim()
        check(poolReadBack == maxPoolPercent.toString()) {
            "zswap max_pool_percent did not take effect: expected $maxPoolPercent, read back '$poolReadBack'"
        }
        println("zSwap enabled: compressor=$compressorReadBack, zpool=$zpoolReadBack, max_pool_percent=$poolReadBack")

        adb.rootShell("mount -t debugfs debugfs /sys/kernel/debug")
    }

    fun initSwapByType() {
        when (config.swapType) {
            ArgType.NO_SWAP.code -> {
                logger.log(LogType.SUMMARY, "config.swapLabel=No Swap")
                disableZram()
            }
            ArgType.ONLY_ZRAM.code -> {
                logger.log(LogType.SUMMARY, "config.swapLabel=Only zRAM")
                enableZram()
            }
            ArgType.ONLY_FLASH_SWAP.code -> {
                logger.log(LogType.SUMMARY, "config.swapLabel=Only Flash Swap")
                disableZram()
                enableFlashSwap(config.flashSwapDeviceSizeMB)
            }
            ArgType.ZSWAP.code, ArgType.ZSWAP_ZBUD.code -> {
                val zbud = config.swapType == ArgType.ZSWAP_ZBUD.code
                logger.log(LogType.SUMMARY, "config.swapLabel=${if (zbud) "zswap(zbud)" else "ZSWAP"}")
                disableZram()
                enableFlashSwap(config.flashSwapDeviceSizeMB)
                enableZswap(
                    maxPoolPercent = config.zswapMaxPoolPercent,
                    zpool = if (zbud) "zbud" else "zsmalloc",
                )
            }
            ArgType.ZRAM_WRITEBACK.code -> {
                logger.log(LogType.SUMMARY, "config.swapLabel=zRAM + writeback")
                val backing = enableMappedZramWriteback(
                    adb = adb,
                    backingSizeMB = config.flashSwapDeviceSizeMB,
                    intervalSec = config.zramWritebackIntervalSec,
                )
                logger.log(
                    LogType.SUMMARY,
                    buildString {
                        appendLine("config.zramBackingAction=${backing.action}")
                        appendLine("config.zramBackingDevice=${backing.backingDevice}")
                        appendLine("config.zramBackingMiB=${backing.sizeMiB}")
                    }.trimEnd(),
                )
            }
        }
        adb.rootShell("""echo 1 > /sys/kernel/mm/swapin_latency/reset""")
        if (config.swapType != ArgType.NO_SWAP.code) {
            adb.rootShell("""echo 1 > /sys/kernel/mm/swapin_latency/enable""")
            adb.rootShell("""echo ${config.swapInLatSampleRate} > /sys/kernel/mm/swapin_latency/sample_rate""")
        }
        // Print what actually took effect so it can be compared with the config.* lines in summary.txt.
        displaySwapConfigsFromPhone()
    }

    fun displaySwapConfigsFromPhone() {
        println("=== swap configuration on device (swapType=${config.swapType}) ===")
        val probes = swapConfigProbes(config.swapType) + dynamicBackingProbes()
        probes.forEach { probe ->
            val result = adb.rootShell(probe.command)
            val text = result.output.trim()
            val body = when {
                text.isNotEmpty() -> text
                result.exitCode != 0 -> "  <unavailable>"
                else -> "  <empty>"
            }
            println("[${probe.label}]")
            println(body)
        }
        println("=== end of swap configuration ===")
    }

    private fun dynamicBackingProbes(): List<SwapConfigProbe> {
        if (config.swapType != ArgType.ZRAM_WRITEBACK.code) return emptyList()
        val backing = adb.rootShell("cat $ZRAM_SYSFS/backing_dev").output.trim()
        return backingLoopProbes(backing)
    }
}

internal fun swapConfigProbes(
    swapType: Int,
    zramSysfs: String = ZRAM_SYSFS,
    flashSwapFile: String = FLASH_SWAP_FILE,
): List<SwapConfigProbe> = buildList {
    add(SwapConfigProbe("proc/swaps", "cat /proc/swaps"))
    add(SwapConfigProbe("selinux", "getenforce"))
    add(SwapConfigProbe("vendor zram props", "getprop | grep -i zram"))
    add(SwapConfigProbe("zram0 disksize", "cat $zramSysfs/disksize"))
    add(SwapConfigProbe("zram0 mm_stat", "cat $zramSysfs/mm_stat"))
    add(SwapConfigProbe("zram0 comp_algorithm", "cat $zramSysfs/comp_algorithm"))

    when (swapType) {
        ArgType.ONLY_FLASH_SWAP.code, ArgType.ZSWAP.code, ArgType.ZSWAP_ZBUD.code ->
            add(SwapConfigProbe("flash swap device", "dmctl table flash_swap"))

        ArgType.ZRAM_WRITEBACK.code -> {
            add(SwapConfigProbe("zram0 backing_dev", "cat $zramSysfs/backing_dev"))
            add(SwapConfigProbe("zram0 bd_stat (4 KiB units)", "cat $zramSysfs/bd_stat"))
            add(
                SwapConfigProbe(
                    "zram0 writeback limit",
                    "for n in writeback_limit_enable writeback_limit; do " +
                        "echo \"\$n=\$(cat $zramSysfs/\$n 2>/dev/null)\"; done",
                ),
            )
            add(SwapConfigProbe("per_boot files", "ls -l /data/per_boot/"))
        }

        else -> Unit // noSwap / onlyZram: the common part already covers them
    }

    if (ArgType.fromCode(swapType)?.usesZswap == true) {
        add(
            SwapConfigProbe(
                "zswap parameters",
                "for n in enabled compressor zpool max_pool_percent; do " +
                    "echo \"\$n=\$(cat /sys/module/zswap/parameters/\$n 2>/dev/null)\"; done",
            ),
        )
        add(
            SwapConfigProbe(
                "zswap counters",
                "for n in stored_pages pool_total_size written_back_pages pool_limit_hit; do " +
                    "echo \"\$n=\$(cat /sys/kernel/debug/zswap/\$n 2>/dev/null)\"; done",
            ),
        )
    }
}

internal fun backingLoopProbes(backingDevice: String): List<SwapConfigProbe> {
    val name = backingDevice.substringAfterLast('/')
    if (!Regex("loop[0-9]+").matches(name)) return emptyList()
    return listOf(
        SwapConfigProbe("$name backing_file", "cat /sys/block/$name/loop/backing_file"),
        SwapConfigProbe(
            "$name dio/blocksize",
            "cat /sys/block/$name/loop/dio /sys/block/$name/queue/logical_block_size",
        ),
        SwapConfigProbe(
            "$name autoclear/size",
            "cat /sys/block/$name/loop/autoclear /sys/block/$name/size",
        ),
    )
}
