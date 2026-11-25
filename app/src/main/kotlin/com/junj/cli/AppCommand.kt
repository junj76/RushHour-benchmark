package com.junj.cli

import com.github.ajalt.clikt.core.CliktCommand
import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.options.required
import com.github.ajalt.clikt.parameters.options.validate
import com.github.ajalt.clikt.parameters.types.long
import com.github.ajalt.clikt.parameters.types.int
import com.junj.config.DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB
import com.junj.config.DEFAULT_ZRAM_WRITEBACK_INTERVAL_SEC
import com.junj.config.DEFAULT_ZSWAP_MAX_POOL_PERCENT
import com.junj.config.ExperimentConfig
import com.junj.domain.app.globalAppInfos
import com.junj.output.logging.getTimeStamp
import java.io.File

enum class ArgType(val code: Int) {
    NO_SWAP(0),
    ONLY_ZRAM(1),

    /**
     * Codes follow the declaration order:
     * 0 = no swap, 1 = zRAM, 2 = zRAM + writeback, 3 = flash swap, 4 = zSwap, 5 = zSwap (zbud).
     * Keep this comment, the `-t` help text and the README table in sync when renumbering;
     * the run directory suffix and every summary.txt rely on these codes.
     */
    ZRAM_WRITEBACK(2),
    ONLY_FLASH_SWAP(3),
    ZSWAP(4),
    ZSWAP_ZBUD(5);

    val usesZswap: Boolean get() = this == ZSWAP || this == ZSWAP_ZBUD

    companion object {
        fun fromCode(code: Int): ArgType? = entries.firstOrNull { it.code == code }
    }
}

class AppCommand : CliktCommand(name = "android-app-launch-test") {
    val actionMode: Int by option("-c", "--action-mode", help = "App actions: 0=Monkey (default), 1=fixed scripts")
        .int()
        .default(0)
        .validate { require(it in 0..1) { "action mode must be 0 (Monkey) or 1 (fixed scripts)" } }

    val appNames: String? by option("--app-names", help = "Comma-separated workload names; must match -a count")
    val rounds: Int by option("--rounds", help = "Number of workload rounds; defaults to 5")
        .int()
        .default(com.junj.config.DEFAULT_TEST_ROUND_COUNT)
        .validate { require(it > 0) { "rounds must be greater than 0" } }

    val type: Int by option(
        "-t",
        "--type",
        help = "Swap type: 0=no swap, 1=zRAM, 2=zRAM + backing device writeback, 3=flash swap, 4=zSwap (zsmalloc), 5=zSwap (zbud)",
    )
        .int()
        .required()
        .validate {
            require(ArgType.fromCode(it) != null) {
                "type must be one of ${ArgType.entries.map { argType -> argType.code }.sorted().joinToString()}"
            }
        }

    val appCount: Int by option(
        "-a",
        "--apps",
        help = "Number of workload entries: 1..${globalAppInfos.size}; selects the first N entries"
    )
        .int()
        .required()
        .validate {
            require(it in 1..globalAppInfos.size) {
                "apps must be between 1 and ${globalAppInfos.size}"
            }
        }

    val logPath: String? by option(
        "-p",
        "--prefix",
        help = "Optional log output path",
    )

    val randomSeed: Int by option(
        "-s",
        "--seed",
        help = "Random seed number for app launch"
    )
        .int()
        .default(0)

    val flashSize: Int? by option(
        "-f",
        "--flash_size",
        help = "Backing storage size in MiB (1024*1024 bytes): the flash swap file for -t ${ArgType.ONLY_FLASH_SWAP.code}/" +
            "${ArgType.ZSWAP.code}/${ArgType.ZSWAP_ZBUD.code}, or the zRAM backing file for -t ${ArgType.ZRAM_WRITEBACK.code}. " +
            "Optional, defaults to $DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB MiB.",
    )
        .int()

    val writebackInterval: Int? by option(
        "-w",
        "--writeback_interval",
        help = "zRAM writeback interval in seconds; only used by -t ${ArgType.ZRAM_WRITEBACK.code}. " +
            "Optional, defaults to $DEFAULT_ZRAM_WRITEBACK_INTERVAL_SEC s.",
    )
        .int()

    val zswapMaxPoolPercent: Int? by option(
        "-m",
        "--max_pool_percent",
        help = "zswap max_pool_percent (percent of RAM); only used by -t ${ArgType.ZSWAP.code}/${ArgType.ZSWAP_ZBUD.code}. " +
            "Optional, defaults to $DEFAULT_ZSWAP_MAX_POOL_PERCENT.",
    )
        .int()

    val zramDisksize: Long? by option("-d", "--zram-disksize",
        help = "zRAM logical swap capacity in MB (MiB, 1024*1024 bytes); -t 1/2 only. Default: current device size.").long()
    val zramMemLimit: Long? by option("-z", "--zram-mem-limit",
        help = "zRAM compressed memory pool limit in MB (MiB, 1024*1024 bytes); -t 1/2 only. Default: 0 (unlimited).").long()

    override fun run() = Unit
}

fun parseArgs(args: Array<String>): ExperimentConfig {
    val command = AppCommand().also { it.main(args) }
    val selectedAppNames = command.appNames?.split(',')?.map { it.trim() }
    if (selectedAppNames != null) {
        require(selectedAppNames.size == command.appCount) { "--app-names count must match -a" }
        require(selectedAppNames.distinct().size == selectedAppNames.size) { "--app-names must not contain duplicates" }
        val knownNames = globalAppInfos.map { it.name }.toSet()
        require(selectedAppNames.all { it in knownNames }) { "Unknown app names: ${selectedAppNames.filterNot { it in knownNames }}" }
    }
    for ((name, value) in listOf("-d" to command.zramDisksize, "-z" to command.zramMemLimit)) {
        if (value != null) {
            require(command.type == 1 || command.type == 2) { "$name is only applicable to -t 1/2 (zRAM)" }
            val minimum = if (name == "-d") 1L else 0L
            require(value in minimum..(Long.MAX_VALUE / 1048576L)) { "$name is outside the supported MiB range" }
        }
    }
    val flashSize = command.flashSize
    if (flashSize != null) {
        require(
            command.type == ArgType.ONLY_FLASH_SWAP.code ||
                ArgType.fromCode(command.type)?.usesZswap == true ||
                command.type == ArgType.ZRAM_WRITEBACK.code
        ) {
            "-f/--flash_size is only applicable to the backing-storage types: " +
                "-t ${ArgType.ONLY_FLASH_SWAP.code} (flash swap), -t ${ArgType.ZSWAP.code}/${ArgType.ZSWAP_ZBUD.code} (zSwap) " +
                "or -t ${ArgType.ZRAM_WRITEBACK.code} (zRAM + writeback)"
        }
        require(flashSize > 0) { "flash_size must be greater than 0, got $flashSize" }
    }
    val flashSwapDeviceSizeMB = flashSize ?: DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB

    val writebackInterval = command.writebackInterval
    if (writebackInterval != null) {
        require(command.type == ArgType.ZRAM_WRITEBACK.code) {
            "-w/--writeback_interval is only applicable to -t ${ArgType.ZRAM_WRITEBACK.code} (zRAM + writeback)"
        }
        require(writebackInterval > 0) {
            "writeback_interval must be greater than 0, got $writebackInterval"
        }
    }
    val zramWritebackIntervalSec = writebackInterval ?: DEFAULT_ZRAM_WRITEBACK_INTERVAL_SEC

    val maxPoolPercent = command.zswapMaxPoolPercent
    if (maxPoolPercent != null) {
        require(ArgType.fromCode(command.type)?.usesZswap == true) {
            "-m/--max_pool_percent is only applicable to -t ${ArgType.ZSWAP.code}/${ArgType.ZSWAP_ZBUD.code} (zSwap)"
        }
        require(maxPoolPercent in 1..100) {
            "max_pool_percent must be between 1 and 100, got $maxPoolPercent"
        }
    }
    val zswapMaxPoolPercent = maxPoolPercent ?: DEFAULT_ZSWAP_MAX_POOL_PERCENT

    val suffix = buildString {
        append("_workload${command.appCount}")
        when (command.type) {
            ArgType.NO_SWAP.code -> append("_noSwap")
            ArgType.ONLY_ZRAM.code -> append("_onlyZram")
            ArgType.ONLY_FLASH_SWAP.code -> append("_flashSwap$flashSwapDeviceSizeMB")
            ArgType.ZSWAP.code -> append("_zswap${flashSwapDeviceSizeMB}_m$zswapMaxPoolPercent")
            ArgType.ZSWAP_ZBUD.code -> append("_zswap(zbud)${flashSwapDeviceSizeMB}_m$zswapMaxPoolPercent")
            ArgType.ZRAM_WRITEBACK.code ->
                append("_zramWriteback${flashSwapDeviceSizeMB}_wb${zramWritebackIntervalSec}s")
        }
        if (command.type == 1 || command.type == 2) {
            if (command.zramDisksize != null || command.zramMemLimit != null) {
                append("_d${command.zramDisksize ?: "device"}_z${command.zramMemLimit ?: 0}")
            }
        }
        command.logPath?.let { append("_$it") }
    }
    val timestamp = getTimeStamp() + suffix

    return ExperimentConfig(
        swapType = command.type,
        actionMode = command.actionMode,
        zramDisksizeMiB = command.zramDisksize,
        zramMemLimitMiB = command.zramMemLimit ?: 0,
        appCount = command.appCount,
        selectedAppNames = selectedAppNames,
        randomSeed = command.randomSeed,
        timestamp = timestamp,
        outputDirectory = File("../logs/$timestamp"),
        flashSwapDeviceSizeMB = flashSwapDeviceSizeMB,
        testRoundCount = command.rounds,
        zramWritebackIntervalSec = zramWritebackIntervalSec,
        zswapMaxPoolPercent = zswapMaxPoolPercent,
    )
}
