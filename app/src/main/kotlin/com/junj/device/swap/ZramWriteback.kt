package com.junj.device.swap

import com.junj.device.adb.AdbExecutor

/** 每轮由 Main 重启后调用；swap_area 是预留的独立分区，映射从扇区 0 开始。 */
internal fun mapFlashDevice(adb: AdbExecutor, sizeMB: Int): String {
    val partition = "/dev/block/by-name/swap_area"
    val capacity = adb.rootShell("blockdev --getsize64 $partition").output.trim().toLongOrNull()
    check(sizeMB > 0 && capacity != null && sizeMB.toLong() * 1024 * 1024 <= capacity) {
        "Invalid swap_area capacity or requested size: $capacity bytes, $sizeMB MiB"
    }
    checkedZramCommand(adb, "dmctl create flash_swap linear 0 ${sizeMB.toLong() * 2048} $partition 0")
    val device = adb.rootShell("dmctl getpath flash_swap").output.trim()
    check(Regex("/dev/block/dm-[0-9]+").matches(device)) { "Invalid flash_swap device: $device" }
    println("$partition -> $device, offset=0, size=$sizeMB MiB")
    return device
}

/** 新的分区后端入口；保留下面原有文件/loop 实现，避免无关的大段重写。 */
fun enableMappedZramWriteback(adb: AdbExecutor, backingSizeMB: Int, intervalSec: Int): ZramBackingDeviceResult {
    require(intervalSec > 0)
    requireZramWritebackSupport(adb)
    val disksize = adb.rootShell("cat $ZRAM_SYSFS/disksize").output.trim()
    check(disksize.toLongOrNull()?.let { it > 0 } == true) { "Invalid zRAM disksize; reboot before retrying" }
    val device = mapFlashDevice(adb, backingSizeMB)
    listOf(
        "swapoff $ZRAM_DEVICE",
        "echo 1 > $ZRAM_SYSFS/reset",
        "echo $COMPRESSION_ALGORITHM > $ZRAM_SYSFS/comp_algorithm",
        "echo $device > $ZRAM_SYSFS/backing_dev",
        "echo $disksize > $ZRAM_SYSFS/disksize",
        "mkswap $ZRAM_DEVICE",
        "swapon $ZRAM_DEVICE",
    ).forEach { checkedZramCommand(adb, it) }
    return ZramBackingDeviceResult("recreated", device, "", backingSizeMB.toLong())
}

/** zram0 的 sysfs 目录。 */
const val ZRAM_SYSFS = "/sys/block/zram0"

/** zram0 的设备节点。 */
const val ZRAM_DEVICE = "/dev/block/zram0"

/** 大小与参数不一致时，本次实验使用的后端文件（厂商自己的那个会被拆掉）。 */
const val ZRAM_BACKING_FILE = "/data/per_boot/zram_backing"

/** reset 前保存逻辑容量；per_boot 保证不会跨开机误用旧配置。 */
internal const val ZRAM_DISKSIZE_CHECKPOINT = "/data/per_boot/rushhour_zram_disksize"

/**
 * 一次 adb 调用扫出所有空闲 loop 设备（`backing_file` 为空的那些）。
 *
 * 设备上的 loop 编号被 APEX 之类占用得很散（tokay 上 zram 自己用的是 loop46），
 * 所以直接扫 `/sys/block/loop*` 而不是猜编号。
 */
internal const val FREE_LOOP_SCAN =
    "for d in /sys/block/loop*; do n=\${d##*/}; b=\$(cat \$d/loop/backing_file 2>/dev/null); " +
        "[ -z \"\$b\" ] && echo \"FREE \$n\"; done"

/** 当前生效的 zRAM 后端设备（Android 开机时通常已经配好一套）。 */
internal data class CurrentBackingDevice(
    /** 例如 `/dev/block/loop46` 或 `/dev/block/sda12`。 */
    val backingDevice: String,
    /** 设备名；只有 loop 才有 `loop/backing_file`。 */
    val loopName: String?,
    /** loop 背后的文件；非 loop 时为空串。 */
    val backingFile: String,
    val sizeBytes: Long,
)

/** 后端设备的处理结果，写进 summary.txt，事后能判断这轮是复用还是重建。 */
data class ZramBackingDeviceResult(
    /** `reused` 或 `recreated`。 */
    val action: String,
    val backingDevice: String,
    val backingFile: String,
    val sizeMiB: Long,
)

/**
 * zRAM writeback 需要内核提供 `/sys/block/zram0/{idle,writeback,backing_dev}`。
 *
 * **不要用 `/proc/config.gz` 判断**：Android 上 zram 常是厂商模块（tokay 的 comp_algorithm 里第一个是
 * 厂商私有的 `lz77eh`，而 GKI 的 config.gz 里写着 `CONFIG_ZRAM_WRITEBACK is not set`），
 * 只有探测节点才作数。缺节点就直接失败，避免跑出"名字叫 zram_writeback、实际什么都没发生"的数据。
 */
fun requireZramWritebackSupport(adb: AdbExecutor) {
    val idle = adb.rootShell("[ -e $ZRAM_SYSFS/idle ] && echo yes || echo no").output.trim()
    val writeback = adb.rootShell("[ -e $ZRAM_SYSFS/writeback ] && echo yes || echo no").output.trim()
    val backing = adb.rootShell("[ -e $ZRAM_SYSFS/backing_dev ] && echo yes || echo no").output.trim()
    check(idle == "yes" && writeback == "yes" && backing == "yes") {
        "zRAM writeback is unavailable on this kernel: $ZRAM_SYSFS/idle=$idle, " +
            "$ZRAM_SYSFS/writeback=$writeback, $ZRAM_SYSFS/backing_dev=$backing. " +
            "需要内核提供这些节点（不要只看 /proc/config.gz，厂商 zram 模块的配置可能与之不同）；" +
            "否则本方案无法生效，数据会被误标为 zram_writeback。"
    }
}

/** 读当前后端设备；没有配置（或读回不是设备路径）时返回 null。 */
internal fun readCurrentBackingDevice(adb: AdbExecutor): CurrentBackingDevice? {
    val backingDevice = adb.rootShell("cat $ZRAM_SYSFS/backing_dev").output.trim()
    if (!backingDevice.startsWith("/dev/")) return null

    val name = backingDevice.substringAfterLast('/')
    val isLoop = name.startsWith("loop")
    val backingFile = if (isLoop) {
        adb.rootShell("cat /sys/block/$name/loop/backing_file").output.trim()
    } else {
        ""
    }
    val sectors = adb.rootShell("cat /sys/block/$name/size").output.trim().toLongOrNull() ?: 0L
    return CurrentBackingDevice(
        backingDevice = backingDevice,
        loopName = name.takeIf { isLoop },
        backingFile = backingFile,
        sizeBytes = sectors * 512L,
    )
}

/**
 * 拆除旧后端的命令。
 *
 * - 只对 loop 生效：厂商如果用裸分区做后端，没有"删除"这一说，直接换掉即可；
 * - 顺序是 **先 `losetup -d` 再 `rm`**：文件被 loop 占着时 `rm` 只是解除链接，空间要等 loop 摘掉才释放；
 * - 只删 `/data/` 下的文件（loop 的后端文件），其它路径一律不碰。
 */
internal fun removeBackingDeviceCommands(current: CurrentBackingDevice): List<String> {
    if (current.loopName == null) return emptyList()
    return buildList {
        add(detachBackingLoopCommand(current))
        if (current.backingFile.startsWith("/data/")) add("rm -f ${quoteShellPath(current.backingFile)}")
    }
}

/** 原生 loop 带 AUTOCLEAR：reset 后可能已自动解绑。必须读回确认，而非忽略所有 detach 错误。 */
internal fun detachBackingLoopCommand(current: CurrentBackingDevice): String {
    val name = requireNotNull(current.loopName)
    require(Regex("loop[0-9]+").matches(name))
    val node = "/sys/block/$name/loop/backing_file"
    val expected = quoteShellPath(current.backingFile)
    val device = quoteShellPath(current.backingDevice)
    return "if [ -e $node ]; then " +
        "b=\$(cat $node) || exit \$?; " +
        "if [ -n \"\$b\" ]; then " +
        "[ \"\$b\" = $expected ] || { echo 'Refusing to detach reused loop $name'; exit 1; }; " +
        "losetup -d $device; fi; fi; " +
        "if [ -e $node ]; then " +
        "b=\$(cat $node) || exit \$?; " +
        "[ -z \"\$b\" ] || { echo 'Loop $name is still attached'; exit 1; }; fi"
}

private fun quoteShellPath(path: String): String = "'" + path.replace("'", "'\\''") + "'"

/**
 * 配置 writeback 的命令序列。
 *
 * 顺序有内核强制的约束，抽成纯函数以便用单测钉住：
 * 1. 先 swapoff（设备正在被使用时改属性会 -EBUSY）；
 * 2. `reset` 复位设备（disksize 归零、已分配内存释放，同时释放对旧后端的引用）；
 * 3. 拆除旧后端（[removeCommands]，必须排在 reset 之后）；
 * 4. 写 `backing_dev`——内核文档明确要求**在设置 disksize 之前**；
 * 5. 恢复 `disksize`，再 mkswap + swapon。
 *
 * mainline 的 `backing_dev` 只接受块设备（不支持直接写文件路径），所以文件要经 loop 设备转一手。
 * 注意 `mem_limit` 是**只写**节点，读不出来，因此这里不去"读原值再恢复"。
 */
internal fun zramWritebackSetupCommands(
    backingSizeMb: Int,
    disksizeBytes: String,
    loopDevice: String,
    removeCommands: List<String> = emptyList(),
    backingFile: String = ZRAM_BACKING_FILE,
    sysfs: String = ZRAM_SYSFS,
    device: String = ZRAM_DEVICE,
    directIoHelper: String = ZRAM_LOOP_DIRECT_IO_HELPER,
    swapActive: Boolean = true,
): List<String> = buildList {
    if (swapActive) add("swapoff $device")
    add("echo 1 > $sysfs/reset")
    // Inherit the zram compression setting: comp_algorithm is only writable while the device
    // is uninitialized, and it must be written before disksize, so it belongs in this window.
    add("echo $COMPRESSION_ALGORITHM > $sysfs/comp_algorithm")
    addAll(removeCommands)
    add("dd if=/dev/zero of=$backingFile bs=1M count=$backingSizeMb")
    add("chmod 600 $backingFile")
    add("losetup $loopDevice $backingFile")
    // 与 Android fs_mgr 一致：LOOP_SET_BLOCK_SIZE(4096)，然后 LOOP_SET_DIRECT_IO(1)。
    add("$directIoHelper $loopDevice")
    add("echo $loopDevice > $sysfs/backing_dev")
    add("echo $disksizeBytes > $sysfs/disksize")
    add("mkswap $device")
    add("swapon $device")
}

internal fun loopBusyProbeCommand(name: String): String =
    "[ -n \"\$(cat /sys/block/$name/loop/backing_file 2>/dev/null)\" ] && echo BUSY || echo FREE"

/** loop 的次设备号由内核配置决定，不能假设等于编号或编号乘 8。 */
private fun ensureLoopDeviceNode(adb: AdbExecutor, device: String, name: String) {
    require(Regex("loop[0-9]+").matches(name))
    checkedZramCommand(adb, "if [ ! -e $device ]; then " +
        "dev=\$(cat /sys/class/block/$name/dev) || exit \$?; " +
        "mknod $device b \"\${dev%:*}\" \"\${dev#*:}\"; fi")
}

internal fun findFreeLoopDevice(adb: AdbExecutor): String {
    val allocated = adb.rootShell("losetup -f").output.trim()
    if (allocated.startsWith("/dev/")) {
        val name = allocated.substringAfterLast('/')
        require(Regex("loop[0-9]+").matches(name)) { "Invalid loop allocation: $allocated" }
        ensureLoopDeviceNode(adb, allocated, name)
        if (name.startsWith("loop") && adb.rootShell(loopBusyProbeCommand(name)).output.trim() == "FREE") {
            return allocated
        }
    }

    val number = adb.rootShell(FREE_LOOP_SCAN).output.lineSequence()
        .map { it.trim() }
        .firstOrNull { it.startsWith("FREE ") }
        ?.removePrefix("FREE ")
        ?.trim()
        ?.removePrefix("loop")
        ?.takeIf { it.isNotEmpty() && it.all { char -> char.isDigit() } }
        ?: error("No free loop device found (losetup -f returned '$allocated', sysfs scan found nothing)")

    val device = "/dev/block/loop$number"
    ensureLoopDeviceNode(adb, device, "loop$number")
    return device
}

/**
 * 按 [backingSizeMB] 把 zram0 配上 writeback 后端设备。
 *
 * 开机时厂商通常已经配了一套（tokay：`/dev/block/loop46 -> /data/per_boot/zram_swap`，1 GiB）：
 * - **大小与参数相同** → 原样复用，zram 一个属性都不改（连 swapoff 突发都不会有）；
 * - **大小不同** → 先 reset 释放引用，摘掉旧 loop 并删掉 `/data` 下的旧文件，再建新的；
 * - 旧后端大小读不出来时**拒绝删除**（宁可报错，也不毁掉一个测不出大小的既有配置）。
 *
 * 关键步骤都以读回为准，不靠退出码猜。
 */
fun enableZramWriteback(adb: AdbExecutor, backingSizeMB: Int, intervalSec: Int): ZramBackingDeviceResult {
    require(backingSizeMB > 0) { "backing device size must be greater than 0, got $backingSizeMB" }
    require(intervalSec > 0) { "writeback interval must be greater than 0, got $intervalSec" }
    requireZramWritebackSupport(adb)

    val requestedBytes = backingSizeMB.toLong() * 1024 * 1024
    val current = readCurrentBackingDevice(adb)

    if (current != null) {
        check(current.sizeBytes > 0) {
            "Cannot verify the size of the current zRAM backing device ${current.backingDevice} " +
                "(size read back as 0). "
        }
        if (current.sizeBytes == requestedBytes) {
            println(
                "Reusing the existing zRAM backing device: ${current.backingDevice}" +
                    (if (current.backingFile.isNotEmpty()) " -> ${current.backingFile}" else "") +
                    " (${current.sizeBytes} B = ${backingSizeMB} MiB)",
            )
            ensureZramBackingDirectIo(adb, current.backingDevice)
            val swaps = adb.rootShell("cat /proc/swaps").output
            check(swaps.contains("zram0")) { "zram0 is not an active swap device:\n$swaps" }
            println(swaps)
            return ZramBackingDeviceResult(
                action = "reused",
                backingDevice = current.backingDevice,
                backingFile = current.backingFile,
                sizeMiB = current.sizeBytes / 1024 / 1024,
            )
        }
        println(
            "Existing zRAM backing device ${current.backingDevice} is ${current.sizeBytes / 1024 / 1024} MiB, " +
                "requested ${backingSizeMB} MiB -> removing the old backing device and rebuilding",
        )
    }

    val disksizeReadback = adb.rootShell("cat $ZRAM_SYSFS/disksize").output.trim()
    val disksizeBytes = if (disksizeReadback == "0") {
        val saved = adb.rootShell("cat $ZRAM_DISKSIZE_CHECKPOINT").output.trim()
        check(saved.toLongOrNull()?.let { it > 0L } == true) {
            "zRAM is reset (disksize=0) and no valid $ZRAM_DISKSIZE_CHECKPOINT exists. " +
                "Previous setup may have failed after reset; reboot to restore the boot configuration before retrying."
        }
        println("Recovering zRAM logical capacity from this boot's checkpoint: $saved bytes")
        saved
    } else disksizeReadback
    check(disksizeBytes.toLongOrNull()?.let { it > 0L } == true) {
        "Refusing to reconfigure zRAM: invalid disksize '$disksizeBytes'"
    }
    val swapActive = adb.rootShell("cat /proc/swaps").output.lineSequence()
        .any { it.trim().split(Regex("\\s+")).firstOrNull() == ZRAM_DEVICE }
    checkedZramCommand(adb, "echo $disksizeBytes > $ZRAM_DISKSIZE_CHECKPOINT")

    val loopDevice = findFreeLoopDevice(adb)
    // 在 swapoff/reset 前确认架构、资源及 helper 部署都正常。
    val directIoHelper = ZramLoopDirectIo.prepare(adb)
    var newLoopAttached = false
    try {
        zramWritebackSetupCommands(
            backingSizeMb = backingSizeMB,
            disksizeBytes = disksizeBytes,
            loopDevice = loopDevice,
            removeCommands = current?.let { removeBackingDeviceCommands(it) }.orEmpty(),
            directIoHelper = directIoHelper,
            swapActive = swapActive,
        ).forEach { command ->
            checkedZramCommand(adb, command)
            if (command == "losetup $loopDevice $ZRAM_BACKING_FILE") newLoopAttached = true
            if (command == "$directIoHelper $loopDevice") {
                // 必须在交给 zram 之前读回确认，不能只依赖 ioctl 退出码。
                requireZramLoopDirectIo(adb, loopDevice)
            }
        }
    } catch (failure: Exception) {
        try {
            val swaps = adb.rootShell("cat /proc/swaps").output
            if (!swaps.lineSequence().any { it.trim().split(Regex("\\s+")).firstOrNull() == ZRAM_DEVICE }) {
                checkedZramCommand(adb, "echo 1 > $ZRAM_SYSFS/reset")
                if (newLoopAttached) {
                    checkedZramCommand(adb, detachBackingLoopCommand(CurrentBackingDevice(
                        loopDevice, loopDevice.substringAfterLast('/'), ZRAM_BACKING_FILE, requestedBytes,
                    )))
                }
                checkedZramCommand(adb, "echo $disksizeBytes > $ZRAM_SYSFS/disksize")
                checkedZramCommand(adb, "mkswap $ZRAM_DEVICE")
                checkedZramCommand(adb, "swapon $ZRAM_DEVICE")
                println("zRAM setup failed; restored active plain zRAM ($disksizeBytes bytes), retry setup to configure backing")
            }
        } catch (recovery: Exception) {
            failure.addSuppressed(recovery)
            println("zRAM recovery also failed; this boot's disksize checkpoint is $ZRAM_DISKSIZE_CHECKPOINT")
        }
        throw failure
    } finally {
        ZramLoopDirectIo.cleanup(adb, directIoHelper)
    }

    // 读回校验：backing_dev 必须真的指到新 loop 上，且大小与参数一致
    val backingDevReadback = adb.rootShell("cat $ZRAM_SYSFS/backing_dev").output.trim()
    check(backingDevReadback == loopDevice) {
        "$ZRAM_SYSFS/backing_dev should be $loopDevice but reads back '$backingDevReadback'"
    }
    val algorithmReadBack = adb.rootShell("cat $ZRAM_SYSFS/comp_algorithm").output.trim()
    check(algorithmReadBack.contains("[$COMPRESSION_ALGORITHM]")) {
        "zRAM compression algorithm is not '$COMPRESSION_ALGORITHM' after writeback setup: $algorithmReadBack"
    }
    val loopName = loopDevice.substringAfterLast('/')
    val loopBackingFile = adb.rootShell("cat /sys/block/$loopName/loop/backing_file").output.trim()
    check(loopBackingFile.endsWith(ZRAM_BACKING_FILE.substringAfterLast('/'))) {
        "Loop device $loopDevice is not backed by $ZRAM_BACKING_FILE (reads back '$loopBackingFile')"
    }
    val newSectors = adb.rootShell("cat /sys/block/$loopName/size").output.trim().toLongOrNull() ?: 0L
    check(newSectors * 512L == requestedBytes) {
        "New backing device $loopDevice is ${newSectors * 512L} bytes, expected $requestedBytes ($backingSizeMB MiB)"
    }
    val swaps = adb.rootShell("cat /proc/swaps").output
    check(swaps.contains("zram0")) { "zram0 is not an active swap device after setup:\n$swaps" }

    println(
        "zRAM writeback ready: backing_dev=$loopDevice -> $ZRAM_BACKING_FILE (${backingSizeMB} MiB), " +
            "disksize=$disksizeBytes, interval=${intervalSec}s" +
            (current?.let { ", replaced ${it.backingDevice}" } ?: ""),
    )
    println(swaps)

    return ZramBackingDeviceResult(
        action = "recreated",
        backingDevice = loopDevice,
        backingFile = ZRAM_BACKING_FILE,
        sizeMiB = backingSizeMB.toLong(),
    )
}

/** 配置失败立即停止，不能在 swapoff/reset/losetup 失败后继续宣告 writeback ready。 */
internal fun checkedZramCommand(adb: AdbExecutor, command: String) {
    val result = adb.rootShell(command)
    check(result.exitCode == 0) {
        "zRAM setup failed: command='$command', exit=${result.exitCode}, output=${result.output.trim()}"
    }
}
