package com.junj.device.swap

import com.junj.device.adb.AdbExecutor
import java.util.Base64

internal const val ZRAM_LOOP_DIRECT_IO_HELPER = "zram-loop-direct-io-arm64"

/** Toybox losetup 没有 --direct-io；使用无 libc 依赖的 helper 复现 fs_mgr 的两个 ioctl。
 * 源码和重建命令：tools/zram-loop-direct-io-arm64.S。仅支持 Android arm64。
 */
internal object ZramLoopDirectIo {
    fun prepare(adb: AdbExecutor): String {
        val architecture = adb.rootShell("uname -m").output.trim()
        check(architecture == "aarch64") {
            "zRAM loop direct I/O helper supports aarch64 only, device reports '$architecture'"
        }
        val bytes = checkNotNull(javaClass.getResourceAsStream("/$ZRAM_LOOP_DIRECT_IO_HELPER")) {
            "Missing bundled $ZRAM_LOOP_DIRECT_IO_HELPER"
        }.use { it.readBytes() }
        val directory = adb.rootShell("mktemp -d /data/local/tmp/rushhour-zram.XXXXXX")
        check(directory.exitCode == 0 && validDirectory(directory.output.trim())) {
            "Cannot create private helper directory: ${directory.output.trim()}"
        }
        val helper = "${directory.output.trim()}/$ZRAM_LOOP_DIRECT_IO_HELPER"
        try {
            val encoded = Base64.getEncoder().encodeToString(bytes)
            checkedZramCommand(adb, "printf '%s' '$encoded' | base64 -d > $helper")
            checkedZramCommand(adb, "chmod 700 $helper")
        } catch (e: Exception) {
            cleanup(adb, helper)
            throw e
        }
        return helper
    }

    fun cleanup(adb: AdbExecutor, helper: String) {
        val directory = helper.substringBeforeLast('/')
        require(validDirectory(directory) && helper == "$directory/$ZRAM_LOOP_DIRECT_IO_HELPER")
        // 只清理由 prepare 创建的私有随机目录和唯一文件，绝不递归删除。
        val result = adb.rootShell("rm -f $helper && rmdir $directory")
        if (result.exitCode != 0) println("zRAM helper cleanup failed: ${result.output.trim()}")
    }

    private fun validDirectory(path: String) =
        Regex("/data/local/tmp/rushhour-zram\\.[A-Za-z0-9]+").matches(path)
}

/** 即使是复用已有后端，也要验证 loop 配置，修复旧版脚本留下的 buffered loop。 */
internal fun ensureZramBackingDirectIo(adb: AdbExecutor, loopDevice: String) {
    val name = loopDevice.substringAfterLast('/')
    if (!name.startsWith("loop")) return // 裸分区没有 loop/direct-I/O 属性。
    require(Regex("loop[0-9]+").matches(name)) { "Invalid loop device: $loopDevice" }
    val sysfs = "/sys/block/$name"
    val dio = adb.rootShell("cat $sysfs/loop/dio").output.trim()
    val blockSize = adb.rootShell("cat $sysfs/queue/logical_block_size").output.trim()
    if (dio != "1" || blockSize != "4096") {
        val helper = ZramLoopDirectIo.prepare(adb)
        try {
            checkedZramCommand(adb, "$helper $loopDevice")
        } finally {
            ZramLoopDirectIo.cleanup(adb, helper)
        }
    }
    requireZramLoopDirectIo(adb, loopDevice)
}

internal fun requireZramLoopDirectIo(adb: AdbExecutor, loopDevice: String) {
    val name = loopDevice.substringAfterLast('/')
    require(Regex("loop[0-9]+").matches(name)) { "Invalid loop device: $loopDevice" }
    val sysfs = "/sys/block/$name"
    val dio = adb.rootShell("cat $sysfs/loop/dio").output.trim()
    val blockSize = adb.rootShell("cat $sysfs/queue/logical_block_size").output.trim()
    check(dio == "1" && blockSize == "4096") {
        "zRAM backing $loopDevice must use direct I/O and 4096-byte blocks (dio='$dio', blockSize='$blockSize'); " +
            "buffered loop writes can be denied by SELinux for kernel -> per_boot_file."
    }
    println("zRAM backing loop verified: $loopDevice dio=$dio blockSize=$blockSize")
}
