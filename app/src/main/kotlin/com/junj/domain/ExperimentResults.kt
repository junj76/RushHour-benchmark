package com.junj.domain

import com.junj.domain.launch.LaunchApplicationItem
import com.junj.domain.metrics.SamplingItem
import com.junj.domain.survival.AppSurvivalResult

class ExperimentResults(
    val launches: MutableList<LaunchApplicationItem> = ArrayList(),
    val samples: MutableList<SamplingItem> = ArrayList(),
    val survivals: MutableList<AppSurvivalResult> = ArrayList(),
)

/**
 * Monotonic time base shared by one benchmark run.
 *
 * The clock is created when the test run starts, so every launch record and
 * every system sample is stamped with the milliseconds elapsed since that
 * moment and both output files can be aligned on the same timeline.
 */
class TestClock {
    private val startNs: Long = System.nanoTime()

    fun elapsedMs(): Long = (System.nanoTime() - startNs) / 1_000_000L

    fun elapsedNs(): Long = System.nanoTime() - startNs
}
