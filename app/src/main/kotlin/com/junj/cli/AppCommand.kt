package com.junj.cli

import com.github.ajalt.clikt.core.CliktCommand
import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.options.required
import com.github.ajalt.clikt.parameters.options.validate
import com.github.ajalt.clikt.parameters.types.int
import com.junj.config.ExperimentConfig
import com.junj.config.DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB
import com.junj.domain.app.AppSetType
import com.junj.output.logging.getTimeStamp
import java.io.File

enum class ArgType {
    NO_SWAP,
    ONLY_ZRAM,
    ONLY_FLASH_SWAP,
    ZSWAP;

    val code: Int
        get() = ordinal
}

class AppCommand : CliktCommand(name = "android-app-launch-test") {
    val type: Int by option(
        "-t",
        "--type",
        help = "Swap type: 0=no swap, 1=zRAM, 2=flash swap, 3=zSwap",
    )
        .int()
        .required()
        .validate {
            require(it in ArgType.NO_SWAP.code..ArgType.ZSWAP.code) {
                "type must be between ${ArgType.NO_SWAP.code} and ${ArgType.ZSWAP.code}"
            }
        }

    val appSetNumber: Int by option(
        "-a",
        "--app-set",
        help = "app set number: 0=light, 1=mid, 2=heavy"
    )
        .int()
        .required()
        .validate {
            require(it in AppSetType.LIGHT.code..AppSetType.HEAVY.code) {
                "app-set must be between ${AppSetType.LIGHT.code} and ${AppSetType.HEAVY.code}"
            }
        }

    val logPath: String? by option(
        "-p",
        "--logPath",
        help = "Optional log output path",
    )

    // 注意：短选项 -s 已被 main 的 --seed（随机种子）占用，这里改用 -f。
    val flashSwapSizeMb: Int? by option(
        "-f",
        "--flash-swap-size-mb",
        help = "flash swap file size in MB (default: $DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB)",
    )
        .int()
        .validate {
            require(it in 64..16_384) {
                "flash-swap-size-mb must be between 64 and 16384 (got $it)"
            }
        }

    val randomSeed: Int by option(
        "-s",
        "--seed",
        help = "Random seed number for app launch"
    )
        .int()
        .default(0)

    override fun run() = Unit
}

fun parseArgs(args: Array<String>): ExperimentConfig {
    val command = AppCommand().also { it.main(args) }
    val suffix = buildString {
        when (command.appSetNumber) {
            AppSetType.LIGHT.code -> append("_light")
            AppSetType.MIDDLE.code -> append("_middle")
            AppSetType.HEAVY.code -> append("_heavy")
        }
        when(command.type) {
            0 -> append("_noSwap")
            1 -> append("_onlyZram")
            2 -> append("_flashSwap")
            3 -> append("_zswap")
        }
        command.logPath?.let { append("_$it") }
    }
    val timestamp = getTimeStamp() + suffix

    return ExperimentConfig(
        swapType = command.type,
        appSetNumber = command.appSetNumber,
        randomSeed = command.randomSeed,
        timestamp = timestamp,
        outputDirectory = File("../logs/$timestamp"),
        flashSwapDeviceSizeMb = command.flashSwapSizeMb ?: DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB,
    )
}
