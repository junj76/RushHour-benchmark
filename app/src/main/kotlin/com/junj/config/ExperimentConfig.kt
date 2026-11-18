package com.junj.config

import java.io.File

/** 默认测试轮数；与 CLI 帮助、测试与 test.sh 的“每组 10 轮”保持一致。 */
const val DEFAULT_TEST_ROUND_COUNT = 10
const val DEFAULT_SAMPLE_INTERVAL_MS = 2_000L
const val DEFAULT_LAUNCH_INTERVAL_MS = 20_000L
const val DEFAULT_COLLECT_DELAY_MS = 18_000L
const val DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB = 4096
/** swap-in 延迟采样的 1/N 抽样率；本机实验用 30（值越大采样开销越低）。 */
const val DEFAULT_SWAP_IN_LAT_SAMPLE_RATE = 30

/** zRAM writeback 的默认间隔（秒）；Android 自己那套是分钟/小时级（ro.zram.*），这里按实验需要做成秒级。 */
const val DEFAULT_ZRAM_WRITEBACK_INTERVAL_SEC = 60

/** zswap max_pool_percent default (percent of RAM); only used by -t 4/5 (zSwap). */
const val DEFAULT_ZSWAP_MAX_POOL_PERCENT = 20

/** HyperHold extent 大小（KB）默认值；实验脚本可用 `--extent` / `extent=...` 覆盖。 */
const val DEFAULT_EXTENT_SIZE_KB = 32

data class ExperimentConfig(
    val swapType: Int,
    val appCount: Int,
    val randomSeed: Int = 0,
    val timestamp: String,
    val outputDirectory: File,
    val testRoundCount: Int = DEFAULT_TEST_ROUND_COUNT,
    val sampleIntervalMs: Long = DEFAULT_SAMPLE_INTERVAL_MS,
    val launchIntervalMs: Long = DEFAULT_LAUNCH_INTERVAL_MS,
    val collectDelayMs: Long = DEFAULT_COLLECT_DELAY_MS,
    val flashSwapDeviceSizeMB: Int = DEFAULT_FLASH_SWAP_DEVICE_SIZE_MB,
    val swapInLatSampleRate: Int = DEFAULT_SWAP_IN_LAT_SAMPLE_RATE,
    val zramWritebackIntervalSec: Int = DEFAULT_ZRAM_WRITEBACK_INTERVAL_SEC,
    val zswapMaxPoolPercent: Int = DEFAULT_ZSWAP_MAX_POOL_PERCENT,
    val extentSizeKb: Int = DEFAULT_EXTENT_SIZE_KB,
)
