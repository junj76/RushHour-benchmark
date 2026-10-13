package com.junj.metrics

import com.junj.domain.ExperimentResults
import com.junj.domain.TestClock
import com.junj.output.logging.LogType
import com.junj.output.logging.Logger
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlin.time.Duration.Companion.milliseconds

class SamplingJob(
    private val collector: MetricsCollector,
    private val results: ExperimentResults,
    private val logger: Logger,
    private val intervalMs: Long,
    private val clock: TestClock,
) {
    fun start(scope: CoroutineScope): Job = scope.launch(Dispatchers.IO) {
        println("Starting sampling job (fixed interval ${intervalMs}ms)")

        var tick = 0L
        var consecutiveFailures = 0
        while (isActive) {
            // 按测试时钟对齐到固定节拍（main 的做法），避免采集耗时导致的节拍漂移
            val waitMs = tick * intervalMs - clock.elapsedMs()
            if (waitMs > 0) delay(waitMs.milliseconds)

            try {
                val item = collector.collect(clock.elapsedMs())
                results.samples += item
                logger.log(LogType.SAMPLE, item)
                consecutiveFailures = 0
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // 单次采样失败不要让整个采样线程退出（否则整轮跑下来一个样本都没有），
                // 但要把原因留在控制台，并记下连续失败的次数。
                consecutiveFailures++
                when {
                    consecutiveFailures <= 3 -> e.printStackTrace()
                    consecutiveFailures % 30 == 1 -> println(
                        "sampling keeps failing (${consecutiveFailures} times in a row): " +
                            "${e.javaClass.simpleName}: ${e.message}"
                    )
                }
            }

            tick = clock.elapsedMs() / intervalMs + 1
        }
    }
}
