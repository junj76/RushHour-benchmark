package com.junj.device.swap

import com.junj.config.ExperimentConfig
import com.junj.device.adb.AdbExecutor
import com.junj.device.adb.CommandResult
import com.junj.output.logging.Logger
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ZswapPoolTest {
    @Test
    fun `zswap defaults to zsmalloc and accepts zbud with the same settings`() {
        for (pool in listOf("zsmalloc", "zbud")) {
            val adb = PoolAdb(pool)
            withController(adb) { controller ->
                if (pool == "zsmalloc") controller.enableZswap(maxPoolPercent = 7)
                else controller.enableZswap(maxPoolPercent = 7, zpool = pool)
            }
            assertTrue("echo $pool > /sys/module/zswap/parameters/zpool" in adb.commands)
            assertTrue("echo lz4 > /sys/module/zswap/parameters/compressor" in adb.commands)
            assertTrue("echo 7 > /sys/module/zswap/parameters/max_pool_percent" in adb.commands)
            assertTrue("echo Y > /sys/module/zswap/parameters/enabled" in adb.commands)
        }
    }

    @Test
    fun `unsupported zbud fails before enabling zswap`() {
        for (adb in listOf(PoolAdb("zsmalloc"), PoolAdb("zbud", writeExitCode = 1))) {
            withController(adb) { controller ->
                val failure = assertFailsWith<IllegalStateException> { controller.enableZswap(zpool = "zbud") }
                assertTrue(failure.message.orEmpty().contains("zpool"))
            }
            assertFalse("echo Y > /sys/module/zswap/parameters/enabled" in adb.commands)
        }
    }

    private fun withController(adb: AdbExecutor, block: (SwapController) -> Unit) {
        val directory = Files.createTempDirectory("zswap-pool-test").toFile()
        try {
            Logger(directory).use { logger ->
                block(SwapController(adb, logger, ExperimentConfig(
                    swapType = 5, appCount = 1, timestamp = "test", outputDirectory = directory,
                )))
            }
        } finally {
            directory.deleteRecursively()
        }
    }

    private class PoolAdb(private val readBack: String, private val writeExitCode: Int = 0) : AdbExecutor {
        val commands = mutableListOf<String>()
        override fun shell(command: String): CommandResult = error("Unexpected unprivileged command: $command")
        override fun rootShell(command: String): CommandResult {
            commands += command
            return when (command) {
                "cat /sys/module/zswap/parameters/zpool" -> CommandResult(0, readBack)
                "cat /sys/module/zswap/parameters/compressor" -> CommandResult(0, "lz4")
                "cat /sys/module/zswap/parameters/max_pool_percent" -> CommandResult(0, "7")
                "echo zbud > /sys/module/zswap/parameters/zpool" -> CommandResult(writeExitCode, "")
                else -> CommandResult(0, "")
            }
        }
    }
}
