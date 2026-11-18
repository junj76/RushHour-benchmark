package com.junj.device.swap

import com.junj.device.adb.ProcessAdbExecutor
import org.junit.jupiter.api.Assumptions.assumeTrue
import java.io.File
import java.util.Base64
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** 显式启用才运行：RUSHHOUR_ZRAM_DEVICE_TEST=1 ./gradlew :app:test --tests '*ZramWritebackDeviceTest' */
class ZramWritebackDeviceTest {
    @Test
    fun `buffered failure and direct IO success on isolated device`() {
        assumeTrue(System.getenv("RUSHHOUR_ZRAM_DEVICE_TEST") == "1")
        val adb = ProcessAdbExecutor
        val helper = ZramLoopDirectIo.prepare(adb)
        try {
            val source = listOf(
                File("tools/verify-zram-direct-io.sh"),
                File("../tools/verify-zram-direct-io.sh"),
            ).first { it.isFile }
            val script = source.readText().replace(
                "HELPER=/data/local/tmp/rushhour-loop-direct-io", "HELPER=$helper",
            )
            val result = adb.rootShell(script)
            println(result.output)
            assertEquals(0, result.exitCode, result.output)
            assertTrue(result.output.contains("dio=0 blocksize=512"), result.output)
            assertTrue(result.output.contains("writebackExit=1"), result.output)
            assertTrue(result.output.contains("dio=1 blocksize=4096"), result.output)
            assertTrue(result.output.contains("writebackExit=0"), result.output)
            assertTrue(result.output.contains("verification PASS"), result.output)
        } finally {
            ZramLoopDirectIo.cleanup(adb, helper)
        }
    }

    /** 明确 opt-in：会修改系统 zram0，最后保留 4 GiB 后端；不启动应用压测。 */
    @Test
    fun `resize autoclear backing from one to four GiB on zram0`() {
        assumeTrue(System.getenv("RUSHHOUR_ZRAM_RESIZE_DEVICE_TEST") == "1")
        val adb = ProcessAdbExecutor
        val initial = enableZramWriteback(adb, 1024, 5)
        assertEquals(1024L, initial.sizeMiB)
        val helper = ZramLoopDirectIo.prepare(adb)
        val flagHelper = helper.substringBeforeLast('/') + "/zram-loop-autoclear-arm64"
        try {
            val bytes = checkNotNull(javaClass.getResourceAsStream("/zram-loop-autoclear-arm64"))
                .use { it.readBytes() }
            val encoded = Base64.getEncoder().encodeToString(bytes)
            checkedZramCommand(adb, "printf '%s' '$encoded' | base64 -d > $flagHelper")
            checkedZramCommand(adb, "chmod 700 $flagHelper")
            checkedZramCommand(adb, "$flagHelper ${initial.backingDevice}")
            val oldLoop = initial.backingDevice.substringAfterLast('/')
            assertEquals("1", adb.rootShell("cat /sys/block/$oldLoop/loop/autoclear").output.trim())
            println("Resize control: old backing=${initial.backingDevice} sizeMiB=1024 autoclear=1")
            val resized = enableZramWriteback(adb, 4096, 5)
            assertEquals("recreated", resized.action)
            assertEquals(4096L, resized.sizeMiB)
            val loop = resized.backingDevice.substringAfterLast('/')
            assertEquals("8388608", adb.rootShell("cat /sys/block/$loop/size").output.trim())
            assertEquals("1", adb.rootShell("cat /sys/block/$loop/loop/dio").output.trim())
            assertEquals("4096", adb.rootShell("cat /sys/block/$loop/queue/logical_block_size").output.trim())
            assertTrue(adb.rootShell("cat /proc/swaps").output.contains("zram0"))
            assertEquals("reused", enableZramWriteback(adb, 4096, 5).action)
            println("Resize verification PASS: 1024 MiB autoclear backing -> 4096 MiB direct I/O backing -> reused")
        } finally {
            checkedZramCommand(adb, "rm -f $flagHelper")
            ZramLoopDirectIo.cleanup(adb, helper)
        }
    }

}
