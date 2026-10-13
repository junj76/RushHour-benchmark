package com.junj.config

import java.io.File

const val DEFAULT_TEST_ROUND_COUNT = 5
const val DEFAULT_SAMPLE_INTERVAL_MS = 2_000L
const val DEFAULT_LAUNCH_INTERVAL_MS = 20_000L
const val DEFAULT_COLLECT_DELAY_MS = 18_000L

/**
 * flash swap 文件大小（MB）。
 *
 * 上游默认 4096MB；本机实测 4GB 时踩过"手机重启/写死"的坑（真因是 /data/per_boot 路径，
 * 现已改用 /data/local/tmp），为稳妥起见本地默认仍取 1024MB。
 * 需要与上游一致时把它改回 `1024 * 4`，或运行时用 `-f <MB>` 覆盖。
 */
const val DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB = 1024

data class ExperimentConfig(
    val swapType: Int,
    val appSetNumber: Int,
    val randomSeed: Int = 0,
    val timestamp: String,
    val outputDirectory: File,
    val testRoundCount: Int = DEFAULT_TEST_ROUND_COUNT,
    val sampleIntervalMs: Long = DEFAULT_SAMPLE_INTERVAL_MS,
    val launchIntervalMs: Long = DEFAULT_LAUNCH_INTERVAL_MS,
    val collectDelayMs: Long = DEFAULT_COLLECT_DELAY_MS,
    val flashSwapDeviceSizeMb: Int = DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB,
)
