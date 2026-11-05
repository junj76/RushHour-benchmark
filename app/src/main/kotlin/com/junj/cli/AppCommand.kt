package com.junj.cli

import com.github.ajalt.clikt.core.CliktCommand
import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.options.required
import com.github.ajalt.clikt.parameters.options.validate
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
     * 0 = no swap, 1 = zRAM, 2 = zRAM + writeback, 3 = flash swap, 4 = zSwap.
     * Keep this comment, the `-t` help text and the README table in sync when renumbering;
     * the run directory suffix and every summary.txt rely on these codes.
     */
    ZRAM_WRITEBACK(2),
    ONLY_FLASH_SWAP(3),
    ZSWAP(4);

    companion object {
        fun fromCode(code: Int): ArgType? = entries.firstOrNull { it.code == code }
    }
}

class AppCommand : CliktCommand(name = "android-app-launch-test") {
    val rounds: Int by option("--rounds", help = "Number of workload rounds; defaults to 10")
        .int()
        .default(com.junj.config.DEFAULT_TEST_ROUND_COUNT)
        .validate { require(it > 0) { "rounds must be greater than 0" } }

    val type: Int by option(
        "-t",
        "--type",
        help = "Swap type: 0=no swap, 1=zRAM, 2=zRAM + backing device writeback, 3=flash swap, 4=zSwap",
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
        help = "Backing storage size in MB: the flash swap file for -t ${ArgType.ONLY_FLASH_SWAP.code}/" +
            "${ArgType.ZSWAP.code}, or the zRAM backing file for -t ${ArgType.ZRAM_WRITEBACK.code}. " +
            "Optional, defaults to $DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB MB.",
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
        help = "zswap max_pool_percent (percent of RAM); only used by -t ${ArgType.ZSWAP.code}. " +
            "Optional, defaults to $DEFAULT_ZSWAP_MAX_POOL_PERCENT.",
    )
        .int()

    override fun run() = Unit
}

fun parseArgs(args: Array<String>): ExperimentConfig {
    val command = AppCommand().also { it.main(args) }
    val flashSize = command.flashSize
    if (flashSize != null) {
        require(
            command.type == ArgType.ONLY_FLASH_SWAP.code ||
                command.type == ArgType.ZSWAP.code ||
                command.type == ArgType.ZRAM_WRITEBACK.code
        ) {
            "-f/--flash_size is only applicable to the backing-storage types: " +
                "-t ${ArgType.ONLY_FLASH_SWAP.code} (flash swap), -t ${ArgType.ZSWAP.code} (zSwap) " +
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
        require(command.type == ArgType.ZSWAP.code) {
            "-m/--max_pool_percent is only applicable to -t ${ArgType.ZSWAP.code} (zSwap)"
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
            ArgType.ZRAM_WRITEBACK.code ->
                append("_zramWriteback${flashSwapDeviceSizeMB}_wb${zramWritebackIntervalSec}s")
        }
        command.logPath?.let { append("_$it") }
    }
    val timestamp = getTimeStamp() + suffix

    return ExperimentConfig(
        swapType = command.type,
        appCount = command.appCount,
        randomSeed = command.randomSeed,
        timestamp = timestamp,
        outputDirectory = File("../logs/$timestamp"),
        flashSwapDeviceSizeMB = flashSwapDeviceSizeMB,
        testRoundCount = command.rounds,
        zramWritebackIntervalSec = zramWritebackIntervalSec,
        zswapMaxPoolPercent = zswapMaxPoolPercent,
    )
}
