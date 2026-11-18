package com.junj.device.swap

import java.nio.file.Files
import org.junit.jupiter.api.condition.EnabledOnOs
import org.junit.jupiter.api.condition.OS
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

// 这些用例通过 /bin/bash 驱动 loop 设备的真实命令，只在 POSIX 主机上有意义。
@EnabledOnOs(OS.LINUX, OS.MAC)
class ZramLoopDetachTest {
    private fun probe(binding: String?, detachBody: (String) -> String): Pair<Int, String> {
        val directory = Files.createTempDirectory("loop-detach-test").toFile()
        try {
            val node = directory.resolve("loop46/loop/backing_file")
            if (binding != null) {
                node.parentFile.mkdirs()
                node.writeText(binding)
            }
            val current = CurrentBackingDevice("/dev/block/loop46", "loop46", "/data/per_boot/zram_swap", 1024)
            val command = detachBackingLoopCommand(current)
                .replace("/sys/block/loop46", directory.resolve("loop46").path)
            val script = "losetup() { ${detachBody(node.path)}; }; $command"
            val process = ProcessBuilder("/bin/bash", "-c", script).redirectErrorStream(true).start()
            val output = process.inputStream.bufferedReader().readText()
            return process.waitFor() to output
        } finally {
            directory.deleteRecursively()
        }
    }

    @Test
    fun `already auto detached loop does not call losetup`() {
        val result = probe(null) { "echo SHOULD_NOT_DETACH; return 1" }
        assertEquals(0, result.first, result.second)
        assertTrue(!result.second.contains("SHOULD_NOT_DETACH"))
    }

    @Test
    fun `ENXIO racing with autoclear is accepted only when readback is unbound`() {
        val result = probe("/data/per_boot/zram_swap") { node -> "rm -f '$node'; return 1" }
        assertEquals(0, result.first, result.second)
    }

    @Test
    fun `real detach failure with bound file still fails`() {
        val result = probe("/data/per_boot/zram_swap") { "return 1" }
        assertEquals(1, result.first, result.second)
        assertTrue(result.second.contains("still attached"))
    }

    @Test
    fun `loop reused by another file is never detached`() {
        val result = probe("/data/apex/important.apex") { "echo SHOULD_NOT_DETACH; return 0" }
        assertEquals(1, result.first, result.second)
        assertTrue(result.second.contains("Refusing to detach reused loop"))
        assertTrue(!result.second.contains("SHOULD_NOT_DETACH"))
    }
}
