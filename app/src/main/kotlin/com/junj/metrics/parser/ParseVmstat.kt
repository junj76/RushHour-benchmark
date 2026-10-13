package com.junj.metrics.parser

data class VmstatResult(
    val vmstatR: Int,
    val vmstatB: Int,
    val vmstatSwpd: Long,
    val vmstatFree: Long,
    val vmstatBuff: Long,
    val vmstatCache: Long,
    val vmstatSi: Long,
    val vmstatSo: Long,
    val vmstatBi: Long,
    val vmstatBo: Long,
    val vmstatIn: Long,
    val vmstatCs: Long,
    val vmstatUs: Int,
    val vmstatSy: Int,
    val vmstatId: Int,
    val vmstatWa: Int,
)

fun parseVmstat(output: String): VmstatResult? {
    val values = output
        .lineSequence()
        .filter { it.isNotBlank() }
        .drop(2)
        .lastOrNull()
        ?.trim()
        ?.split(Regex("""\s+"""))
        ?: return null

    if (values.size < 16) return null

    return runCatching {
        VmstatResult(
            vmstatR = values[0].toInt(),
            vmstatB = values[1].toInt(),
            vmstatSwpd = values[2].toLong(),
            vmstatFree = values[3].toLong(),
            vmstatBuff = values[4].toLong(),
            vmstatCache = values[5].toLong(),
            vmstatSi = values[6].toLong(),
            vmstatSo = values[7].toLong(),
            vmstatBi = values[8].toLong(),
            vmstatBo = values[9].toLong(),
            vmstatIn = values[10].toLong(),
            vmstatCs = values[11].toLong(),
            vmstatUs = values[12].toInt(),
            vmstatSy = values[13].toInt(),
            vmstatId = values[14].toInt(),
            vmstatWa = values[15].toInt(),
        )
    }.getOrNull()
}
