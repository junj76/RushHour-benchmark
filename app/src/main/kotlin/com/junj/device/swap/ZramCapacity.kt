package com.junj.device.swap

import com.junj.device.adb.AdbExecutor

data class ZramCapacity(val disksizeBytes: Long, val memLimitBytes: Long, val mmStat: String)

internal fun zramMiBToBytes(value: Long): Long {
    require(value in 0..(Long.MAX_VALUE / 1048576L)) { "Invalid zRAM capacity in MiB: $value" }
    return value * 1048576L
}

internal fun resolveZramDisksize(adb: AdbExecutor, requestedMiB: Long?): Long {
    if (requestedMiB != null) {
        require(requestedMiB > 0) { "zRAM disksize must be positive" }
        return zramMiBToBytes(requestedMiB)
    }
    val result = adb.rootShell("cat $ZRAM_SYSFS/disksize")
    val bytes = result.output.trim().toLongOrNull()
    check(result.exitCode == 0 && bytes != null && bytes > 0) {
        "Invalid current zRAM disksize; specify -d or reboot before retrying"
    }
    return bytes
}

/** mm_stat exposes mem_limit as its fourth field; the mem_limit node itself is write-only. */
internal fun verifyZramCapacity(adb: AdbExecutor, disksizeBytes: Long, memLimitBytes: Long): ZramCapacity {
    val size = adb.rootShell("cat $ZRAM_SYSFS/disksize")
    check(size.exitCode == 0 && size.output.trim().toLongOrNull() == disksizeBytes) {
        "zRAM disksize did not take effect: expected $disksizeBytes, got ${size.output.trim()}"
    }
    val stats = adb.rootShell("cat $ZRAM_SYSFS/mm_stat")
    val limit = stats.output.trim().split(Regex("""\s+""")).getOrNull(3)?.toLongOrNull()
    check(stats.exitCode == 0 && limit == memLimitBytes) {
        "zRAM mem_limit did not take effect: expected $memLimitBytes, mm_stat=${stats.output.trim()}"
    }
    println("zRAM capacity verified: disksizeBytes=$disksizeBytes, memLimitBytes=$memLimitBytes")
    return ZramCapacity(disksizeBytes, memLimitBytes, stats.output.trim())
}
