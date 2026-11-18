package com.junj.device.swap

import com.junj.device.adb.AdbExecutor
import com.junj.device.adb.CommandResult
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class ZramWritebackTest {
    @Test
    fun `mapped writeback uses partition offset zero and sets backing before disksize`() {
        val adb = supportingAdb(mapOf(
            "cat $ZRAM_SYSFS/disksize" to listOf("6054678528"),
            "blockdev --getsize64 /dev/block/by-name/swap_area" to listOf("17179869184"),
            "dmctl getpath flash_swap" to listOf("/dev/block/dm-13"),
        ))
        val result = enableMappedZramWriteback(adb, 4096, 30)
        assertEquals("/dev/block/dm-13", result.backingDevice)
        assertTrue(adb.issued.contains("dmctl create flash_swap linear 0 8388608 /dev/block/by-name/swap_area 0"))
        val reset = adb.issued.indexOf("echo 1 > $ZRAM_SYSFS/reset")
        val backing = adb.issued.indexOf("echo /dev/block/dm-13 > $ZRAM_SYSFS/backing_dev")
        val size = adb.issued.indexOf("echo 6054678528 > $ZRAM_SYSFS/disksize")
        assertTrue(reset >= 0 && reset < backing && backing < size)
        assertEquals("swapon $ZRAM_DEVICE", adb.issued.last())
        assertTrue(adb.issued.none { it.startsWith("dd ") || it.startsWith("losetup ") })
    }

    @Test
    fun `mapping refuses an oversized request before creating the device`() {
        val adb = FakeAdb(mapOf("blockdev --getsize64 /dev/block/by-name/swap_area" to listOf("1073741824")))
        assertFailsWith<IllegalStateException> { mapFlashDevice(adb, 4096) }
        assertTrue(adb.issued.none { it.startsWith("dmctl create") })
    }

    // ------------------------------------------------------------ 命令序列（纯函数）

    @Test
    fun `swapoff, reset, loop and backing_dev all happen before disksize`() {
        val commands = setupCommands()
        val reset = commands.indexOfFirst { it.contains("/reset") }
        val loopSetup = commands.indexOfFirst { it.startsWith("losetup") }
        val backingDev = commands.indexOfFirst { it.contains("$ZRAM_SYSFS/backing_dev") }
        val disksize = commands.indexOfFirst { it.contains("$ZRAM_SYSFS/disksize") }

        assertTrue(commands.first().startsWith("swapoff"), commands.toString())
        assertTrue(reset in 0..<loopSetup, "reset 要在挂 loop 之前：$commands")
        assertTrue(loopSetup in 0..<backingDev, "loop 要先挂好：$commands")
        assertTrue(backingDev in 0..<disksize, "backing_dev 必须在 disksize 之前（内核文档要求）：$commands")
        assertTrue(commands.last().startsWith("swapon"), commands.toString())
    }

    @Test
    fun `removal of the old backing device sits after reset and before the new file`() {
        val old = CurrentBackingDevice(
            backingDevice = "/dev/block/loop46",
            loopName = "loop46",
            backingFile = "/data/per_boot/zram_swap",
            sizeBytes = 1_073_741_824L,
        )
        val commands = zramWritebackSetupCommands(
            backingSizeMb = 2048,
            disksizeBytes = "4194304",
            loopDevice = "/dev/block/loop7",
            removeCommands = removeBackingDeviceCommands(old),
        )
        val reset = commands.indexOfFirst { it.contains("/reset") }
        val detachCommand = commands.first { it.contains("losetup -d '/dev/block/loop46'") }
        assertTrue(
            detachCommand.contains("loop/backing_file") && detachCommand.contains("still attached"),
            "摘 loop 前要先判断它是否已被 autoclear 自动 detach：$commands",
        )
        val detach = commands.indexOfFirst { it.contains("losetup -d '/dev/block/loop46'") }
        val delete = commands.indexOfFirst { it.contains("rm -f") && it.contains("/data/per_boot/zram_swap") }
        val create = commands.indexOfFirst { it.startsWith("dd ") }

        assertTrue(reset in 0..<detach, "reset 先释放 zram 对旧后端的引用：$commands")
        assertTrue(detach in 0..<delete, "先摘 loop 再删文件，否则空间不释放：$commands")
        assertTrue(delete in 0..<create, "删旧的要在建新的之前：$commands")
    }

    @Test
    fun `backing file size comes from the parameter`() {
        assertTrue(setupCommands(backingSizeMb = 1024).any { it.contains("count=1024") })
        assertTrue(setupCommands(backingSizeMb = 2048).any { it.contains("count=2048") })
    }

    @Test
    fun `never touches the write-only mem_limit node`() {
        assertTrue(setupCommands().none { it.contains("mem_limit") }, "mem_limit 是只写节点，不能读也不能乱写")
    }

    @Test
    fun `never removes a raw partition backing device`() {
        val partition = CurrentBackingDevice(
            backingDevice = "/dev/block/sda12",
            loopName = null,
            backingFile = "",
            sizeBytes = 512L * 1024,
        )

        assertEquals(emptyList(), removeBackingDeviceCommands(partition))
    }

    // ------------------------------------------------------------ 前置校验

    @Test
    fun `refuses to run when the kernel lacks the writeback nodes`() {
        val adb = unsupportedAdb()

        val error = assertFailsWith<IllegalStateException> { requireZramWritebackSupport(adb) }

        assertTrue(error.message!!.contains("config.gz"), error.message!!)
    }

    @Test
    fun `accepts a kernel that provides the writeback nodes`() {
        requireZramWritebackSupport(supportingAdb())
    }

    @Test
    fun `checks the kernel before touching swap`() {
        val adb = unsupportedAdb()

        assertFailsWith<IllegalStateException> { enableZramWriteback(adb, backingSizeMB = 1024, intervalSec = 30) }

        assertTrue(adb.issued.none { it.startsWith("swapoff") }, "不该在确认内核支持之前就 swapoff：${adb.issued}")
    }

    // ------------------------------------------------------------ 复用 / 重建

    @Test
    fun `reuses the boot backing device when the requested size matches`() {
        val adb = supportingAdb(
            mapOf(
                "cat $ZRAM_SYSFS/backing_dev" to listOf("/dev/block/loop46"),
                "cat /sys/block/loop46/loop/backing_file" to listOf("/data/per_boot/zram_swap"),
                "cat /sys/block/loop46/size" to listOf("2097152"),         // 1 GiB
                "cat /proc/swaps" to listOf("/dev/block/zram0 partition 3868872 1707776 -2"),
            ),
        )

        val result = enableZramWriteback(adb, backingSizeMB = 1024, intervalSec = 30)

        assertEquals("reused", result.action)
        assertEquals("/dev/block/loop46", result.backingDevice)
        assertEquals("/data/per_boot/zram_swap", result.backingFile)
        assertEquals(1024L, result.sizeMiB)
        assertTrue(adb.issued.none { it.startsWith("swapoff") }, "复用路径不该动 zram：${adb.issued}")
        assertTrue(adb.issued.none { it.contains("rm -f") }, "复用路径不该删东西：${adb.issued}")
        assertTrue(adb.issued.none { it.startsWith("dd ") }, "复用路径不该重建文件：${adb.issued}")
    }

    @Test
    fun `removes the old backing device and rebuilds when the size differs`() {
        val adb = supportingAdb(
            mapOf(
                "cat $ZRAM_SYSFS/backing_dev" to listOf("/dev/block/loop46", "/dev/block/loop7"),
                "cat /sys/block/loop46/loop/backing_file" to listOf("/data/per_boot/zram_swap"),
                "cat /sys/block/loop46/size" to listOf("2097152"),         // 1 GiB
                "cat $ZRAM_SYSFS/disksize" to listOf("3961729024"),
                FREE_LOOP_SCAN to listOf("FREE 7"),
                "cat /sys/block/loop7/loop/backing_file" to listOf("/data/per_boot/zram_backing"),
                "cat /sys/block/loop7/size" to listOf("4194304"),          // 2 GiB
                "cat /proc/swaps" to listOf("/dev/block/zram0 partition 3868872 1707776 -2"),
            ),
        )

        val result = enableZramWriteback(adb, backingSizeMB = 2048, intervalSec = 30)

        assertEquals("recreated", result.action)
        assertEquals("/dev/block/loop7", result.backingDevice)
        assertEquals(2048L, result.sizeMiB)
        assertTrue(adb.issued.any { it.contains("losetup -d '/dev/block/loop46'") }, "旧 loop 要摘掉：${adb.issued}")
        assertTrue(
            adb.issued.any { it.contains("rm -f") && it.contains("/data/per_boot/zram_swap") },
            "旧文件要删掉：${adb.issued}",
        )
        assertTrue(
            adb.issued.contains("dd if=/dev/zero of=/data/per_boot/zram_backing bs=1M count=2048"),
            "按新大小建文件：${adb.issued}",
        )
    }

    @Test
    fun `refuses to remove a backing device whose size cannot be read`() {
        val adb = supportingAdb(
            mapOf(
                "cat $ZRAM_SYSFS/backing_dev" to listOf("/dev/block/loop46"),
                "cat /sys/block/loop46/loop/backing_file" to listOf("/data/per_boot/zram_swap"),
                "cat /sys/block/loop46/size" to listOf("0"),
            ),
        )

        assertFailsWith<IllegalStateException> { enableZramWriteback(adb, backingSizeMB = 1024, intervalSec = 30) }

        assertTrue(adb.issued.none { it.contains("rm -f") }, "测不出大小就不该拆：${adb.issued}")
    }

    // ------------------------------------------------------------ loop 设备

    @Test
    fun `prefers losetup -f over scanning sysfs`() {
        // tokay 实测：静态 16 个 loop 全被 APEX 占满，只有 loop-control 能给出空闲设备（loop47）
        val adb = FakeAdb(
            mapOf(
                "losetup -f" to listOf("/dev/block/loop47"),
                loopBusyProbeCommand("loop47") to listOf("FREE"),
            ),
        )

        assertEquals("/dev/block/loop47", findFreeLoopDevice(adb))
        assertTrue(adb.issued.none { it == FREE_LOOP_SCAN }, "losetup -f 成功时不该再扫 sysfs：${adb.issued}")
    }

    @Test
    fun `falls back to the sysfs scan when losetup cannot allocate`() {
        val adb = FakeAdb(
            mapOf(
                "losetup -f" to listOf(""),
                FREE_LOOP_SCAN to listOf("FREE 7\nFREE 3\n"),
            ),
        )

        assertEquals("/dev/block/loop7", findFreeLoopDevice(adb))
    }

    @Test
    fun `fails when neither strategy finds a loop device`() {
        val adb = FakeAdb(mapOf("losetup -f" to listOf(""), FREE_LOOP_SCAN to listOf("")))

        assertFailsWith<IllegalStateException> { findFreeLoopDevice(adb) }
    }

    @Test
    fun `failed setup command includes command exit and diagnostic`() {
        val adb = object : AdbExecutor {
            override fun shell(command: String) = rootShell(command)
            override fun rootShell(command: String) = CommandResult(1, "Permission denied")
        }
        val error = assertFailsWith<IllegalStateException> {
            checkedZramCommand(adb, "losetup /dev/block/loop7 $ZRAM_BACKING_FILE")
        }
        assertTrue(error.message!!.contains("losetup"))
        assertTrue(error.message!!.contains("exit=1"))
        assertTrue(error.message!!.contains("Permission denied"))
    }

    @Test
    fun `setup stops immediately when swapoff fails`() {
        val issued = mutableListOf<String>()
        val delegate = supportingAdb(
            mapOf(
                "cat /proc/swaps" to listOf("/dev/block/zram0 partition 3868872 1707776 -2"),
                "cat $ZRAM_SYSFS/backing_dev" to listOf("none"),
                "cat $ZRAM_SYSFS/disksize" to listOf("3961729024"),
                "losetup -f" to listOf("/dev/block/loop47"),
                loopBusyProbeCommand("loop47") to listOf("FREE"),
            ),
        )
        val adb = object : AdbExecutor {
            override fun shell(command: String) = rootShell(command)
            override fun rootShell(command: String): CommandResult {
                issued += command
                return if (command.contains("swapoff /dev/block/zram0")) CommandResult(1, "busy")
                    else delegate.rootShell(command)
            }
        }
        assertFailsWith<IllegalStateException> { enableZramWriteback(adb, 1024, 30) }
        assertTrue(issued.none { it.contains("/reset") || it.startsWith("dd ") })
    }

    @Test
    fun `direct IO is configured after loop attach and before backing_dev`() {
        val commands = setupCommands()
        val attach = commands.indexOfFirst { it.startsWith("losetup ") }
        val directIo = commands.indexOf("$ZRAM_LOOP_DIRECT_IO_HELPER /dev/block/loop7")
        val backing = commands.indexOf("echo /dev/block/loop7 > $ZRAM_SYSFS/backing_dev")
        assertTrue(attach in 0..<directIo)
        assertTrue(directIo in 0..<backing)
    }

    @Test
    fun `repairs buffered loop when reusing the same backing size`() {
        val adb = supportingAdb(
            mapOf(
                "cat $ZRAM_SYSFS/backing_dev" to listOf("/dev/block/loop46"),
                "cat /sys/block/loop46/loop/backing_file" to listOf(ZRAM_BACKING_FILE),
                "cat /sys/block/loop46/size" to listOf("2097152"),
                "cat /sys/block/loop46/loop/dio" to listOf("0", "1"),
                "cat /sys/block/loop46/queue/logical_block_size" to listOf("512", "4096"),
                "cat /proc/swaps" to listOf("/dev/block/zram0 partition 3868872 1707776 -2"),
            ),
        )
        enableZramWriteback(adb, 1024, 30)
        assertTrue(adb.issued.any { it.endsWith("/$ZRAM_LOOP_DIRECT_IO_HELPER /dev/block/loop46") })
        assertTrue(adb.issued.none { it.startsWith("swapoff") || it.startsWith("dd ") })
    }

    @Test
    fun `rejects buffered loop even if helper reports success`() {
        val adb = FakeAdb(mapOf("cat /sys/block/loop47/loop/dio" to listOf("0")))
        val error = assertFailsWith<IllegalStateException> { ensureZramBackingDirectIo(adb, "/dev/block/loop47") }
        assertTrue(error.message!!.contains("dio='0'"))
        assertTrue(adb.issued.any { it.startsWith("rm -f /data/local/tmp/rushhour-zram.") })
    }

    @Test
    fun `refuses unsupported helper architecture before swapoff`() {
        val adb = supportingAdb(
            mapOf(
                "cat $ZRAM_SYSFS/backing_dev" to listOf("none"),
                "cat $ZRAM_SYSFS/disksize" to listOf("3961729024"),
                "losetup -f" to listOf("/dev/block/loop47"),
                loopBusyProbeCommand("loop47") to listOf("FREE"),
                "uname -m" to listOf("x86_64"),
            ),
        )
        assertFailsWith<IllegalStateException> { enableZramWriteback(adb, 1024, 30) }
        assertTrue(adb.issued.none { it.startsWith("swapoff") })
    }

    @Test
    fun `reset state recovers saved capacity and does not swapoff inactive zram`() {
        val adb = supportingAdb(mapOf(
            "cat $ZRAM_SYSFS/backing_dev" to listOf("none", "/dev/block/loop47"),
            "cat $ZRAM_SYSFS/disksize" to listOf("0"),
            "cat $ZRAM_DISKSIZE_CHECKPOINT" to listOf("3961729024"),
            "cat /proc/swaps" to listOf("Filename Type Size Used Priority", "/dev/block/zram0 partition 3868872 0 -2"),
            "losetup -f" to listOf("/dev/block/loop47"),
            loopBusyProbeCommand("loop47") to listOf("FREE"),
            "cat /sys/block/loop47/loop/backing_file" to listOf(ZRAM_BACKING_FILE),
            "cat /sys/block/loop47/size" to listOf("8388608"),
        ))
        val result = enableZramWriteback(adb, 4096, 5)
        assertEquals(4096L, result.sizeMiB)
        assertTrue(adb.issued.none { it.startsWith("swapoff ") })
        assertTrue(adb.issued.contains("echo 3961729024 > $ZRAM_SYSFS/disksize"))
    }

    @Test
    fun `missing checkpoint refuses to guess reset logical capacity`() {
        val adb = supportingAdb(mapOf(
            "cat $ZRAM_SYSFS/backing_dev" to listOf("none"),
            "cat $ZRAM_SYSFS/disksize" to listOf("0"),
        ))
        assertFailsWith<IllegalStateException> { enableZramWriteback(adb, 4096, 5) }
        assertTrue(adb.issued.none { it.startsWith("swapoff ") || it.startsWith("dd ") })
    }

    // ------------------------------------------------------------ 辅助

    private fun setupCommands(
        backingSizeMb: Int = 4096,
        disksizeBytes: String = "4194304",
        loopDevice: String = "/dev/block/loop7",
    ) = zramWritebackSetupCommands(
        backingSizeMb = backingSizeMb,
        disksizeBytes = disksizeBytes,
        loopDevice = loopDevice,
    )

    private fun supportResponses(): Map<String, List<String>> = mapOf(
        "[ -e $ZRAM_SYSFS/idle ] && echo yes || echo no" to listOf("yes"),
        "[ -e $ZRAM_SYSFS/writeback ] && echo yes || echo no" to listOf("yes"),
        "[ -e $ZRAM_SYSFS/backing_dev ] && echo yes || echo no" to listOf("yes"),
    )

    private fun unsupportedAdb(): FakeAdb = FakeAdb(
        mapOf(
            "[ -e $ZRAM_SYSFS/idle ] && echo yes || echo no" to listOf("no"),
            "[ -e $ZRAM_SYSFS/writeback ] && echo yes || echo no" to listOf("no"),
            "[ -e $ZRAM_SYSFS/backing_dev ] && echo yes || echo no" to listOf("no"),
        ),
    )

    private fun supportingAdb(extra: Map<String, List<String>> = emptyMap()): FakeAdb =
        FakeAdb(supportResponses() + extra)

    /** 同一命令可以按顺序返回不同结果（例如配置前后各读一次 backing_dev），用完后重复最后一个。 */
    private class FakeAdb(private val responses: Map<String, List<String>> = emptyMap()) : AdbExecutor {
        val issued = mutableListOf<String>()
        private val cursors = mutableMapOf<String, Int>()

        override fun shell(command: String): CommandResult = run(command)

        override fun rootShell(command: String): CommandResult = run(command)

        private fun run(command: String): CommandResult {
            issued += command
            val defaults = when {
                command == "cat /proc/swaps" -> listOf("/dev/block/zram0 partition 3868872 1707776 -2")
                command == "uname -m" -> listOf("aarch64")
                command == "mktemp -d /data/local/tmp/rushhour-zram.XXXXXX" -> listOf("/data/local/tmp/rushhour-zram.Test123")
                command.endsWith("/loop/dio") -> listOf("1")
                command.endsWith("/queue/logical_block_size") -> listOf("4096")
                // comp_algorithm marks the active algorithm in brackets; the writeback path now
                // verifies it inherited the zram setting.
                command.endsWith("/comp_algorithm") -> listOf("[$COMPRESSION_ALGORITHM] lz77eh zstd lz4")
                else -> listOf("")
            }
            val values = responses[command] ?: defaults
            val index = (cursors[command] ?: 0).coerceAtMost(values.lastIndex)
            cursors[command] = index + 1
            return CommandResult(0, values[index])
        }
    }
}
