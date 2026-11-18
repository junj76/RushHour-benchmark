package com.junj.metrics.parser

enum class CommandType {
    AM_START,
    CAT_PROC_MEMINFO,
    CAT_PROC_PRESSURE_MEMORY,
    DUMPSYS_THERMALSERVICE,
    DUMPSYS_GFXINFO,
    DUMPSYS_MEMINFO,
    SWAP_IN_STATS,
}

enum class ResultField {
    // AM_START
    LAUNCH_STATE,
    TOTAL_TIME,
    WAIT_TIME,
    STATUS,

    // CAT_PROC_MEMINFO
    MEM_TOTAL,
    MEM_FREE,
    MEM_AVAILABLE,
    SWAP_TOTAL,
    SWAP_FREE,
    SWAP_CACHED,

    // CAT_PROC_PRESSURE_MEMORY
    PSI_SOME_TOTAL,
    PSI_FULL_TOTAL,

    // DUMPSYS_THERMALSERVICE
    BIG_TEMP,
    MID_TEMP,
    LITTLE_TEMP,
    SOC_THERM_TEMP,
    VIRTUAL_SKIN_TEMP,

    // DUMPSYS_GFX_INFO
    JANKY_FRAMES_PCT,
    P50_RENDER_LAT,
    P90_RENDER_LAT,
    P95_RENDER_LAT,
    P99_RENDER_LAT,

    // DUMPSYS_MEMINFO
    TOTAL_PSS,

    // SWAP_IN_STATS
    TOTAL_SWAP_INS,
    SAMPLED_SWAP_INS,
    AVG_SWAP_IN_LAT,
    P90_SWAP_IN_LAT,
    P99_SWAP_IN_LAT,
    MAX_SWAP_IN_LAT,
}

data class RegexKey(
    val commandType: CommandType,
    val resultField: ResultField,
)

val commandRegexes = mapOf(
    // AM_START
    RegexKey(
        CommandType.AM_START,
        ResultField.LAUNCH_STATE
    ) to Regex("""LaunchState:\s(.+)"""),

    RegexKey(
        CommandType.AM_START,
        ResultField.TOTAL_TIME
    ) to Regex("""TotalTime:\s(.+)"""),

    RegexKey(
        CommandType.AM_START,
        ResultField.WAIT_TIME
    ) to Regex("""WaitTime:\s(.+)"""),

    RegexKey(
        CommandType.AM_START,
        ResultField.STATUS
    ) to Regex("""Status:\s(.+)"""),

    // CAT_PROC_MEMINFO
    RegexKey(
        CommandType.CAT_PROC_MEMINFO,
        ResultField.MEM_TOTAL
    ) to Regex("""MemTotal:\s*(\d+)\skB"""),

    RegexKey(
        CommandType.CAT_PROC_MEMINFO,
        ResultField.MEM_FREE
    ) to Regex("""MemFree:\s*(\d+)\skB"""),

    RegexKey(
        CommandType.CAT_PROC_MEMINFO,
        ResultField.MEM_AVAILABLE
    ) to Regex("""MemAvailable:\s*(\d+)\skB"""),

    RegexKey(
        CommandType.CAT_PROC_MEMINFO,
        ResultField.SWAP_TOTAL
    ) to Regex("""SwapTotal:\s*(\d+)\skB"""),

    RegexKey(
        CommandType.CAT_PROC_MEMINFO,
        ResultField.SWAP_FREE
    ) to Regex("""SwapFree:\s*(\d+)\skB"""),

    RegexKey(
        CommandType.CAT_PROC_MEMINFO,
        ResultField.SWAP_CACHED
    ) to Regex("""SwapCached:\s*(\d+)\skB"""),

    // CAT_PROC_PRESSURE_MEMORY
    RegexKey(
        CommandType.CAT_PROC_PRESSURE_MEMORY,
        ResultField.PSI_SOME_TOTAL
    ) to Regex("""some\s.*?total=(\d+)"""),

    RegexKey(
        CommandType.CAT_PROC_PRESSURE_MEMORY,
        ResultField.PSI_FULL_TOTAL
    ) to Regex("""full\s.*?total=(\d+)"""),

    // DUMPSYS_THERMALSERVICE
    RegexKey(
        CommandType.DUMPSYS_THERMALSERVICE,
        ResultField.BIG_TEMP
    ) to Regex("""Temperature\{mValue=(\d+(?:\.\d+)?),\smType=-?\d+,\smName=BIG,\smStatus=-?\d+\}"""),

    RegexKey(
        CommandType.DUMPSYS_THERMALSERVICE,
        ResultField.MID_TEMP
    ) to Regex("""Temperature\{mValue=(\d+(?:\.\d+)?),\smType=-?\d+,\smName=MID,\smStatus=-?\d+\}"""),

    RegexKey(
        CommandType.DUMPSYS_THERMALSERVICE,
        ResultField.LITTLE_TEMP
    ) to Regex("""Temperature\{mValue=(\d+(?:\.\d+)?),\smType=-?\d+,\smName=LITTLE,\smStatus=-?\d+\}"""),

    RegexKey(
        CommandType.DUMPSYS_THERMALSERVICE,
        ResultField.SOC_THERM_TEMP
    ) to Regex("""Temperature\{mValue=(\d+(?:\.\d+)?),\smType=-?\d+,\smName=soc_therm,\smStatus=-?\d+\}"""),

    RegexKey(
        CommandType.DUMPSYS_THERMALSERVICE,
        ResultField.VIRTUAL_SKIN_TEMP
    ) to Regex("""Temperature\{mValue=(\d+(?:\.\d+)?),\smType=-?\d+,\smName=VIRTUAL-SKIN,\smStatus=-?\d+\}"""),

    RegexKey(
        CommandType.DUMPSYS_GFXINFO,
        ResultField.JANKY_FRAMES_PCT
    ) to Regex("""Janky frames:\s+\d+\s+\((\d+(?:\.\d+)?)%\)"""),

    RegexKey(
        CommandType.DUMPSYS_GFXINFO,
        ResultField.P50_RENDER_LAT
    ) to Regex("""50th\spercentile:\s(\d+)ms"""),

    RegexKey(
        CommandType.DUMPSYS_GFXINFO,
        ResultField.P90_RENDER_LAT
    ) to Regex("""90th\spercentile:\s(\d+)ms"""),

    RegexKey(
        CommandType.DUMPSYS_GFXINFO,
        ResultField.P95_RENDER_LAT
    ) to Regex("""95th\spercentile:\s(\d+)ms"""),

    RegexKey(
        CommandType.DUMPSYS_GFXINFO,
        ResultField.P99_RENDER_LAT
    ) to Regex("""99th\spercentile:\s(\d+)ms"""),

    RegexKey(
        CommandType.DUMPSYS_MEMINFO,
        ResultField.TOTAL_PSS
    ) to Regex("""TOTAL\sPSS:\s*(\d+)"""),

    RegexKey(
        CommandType.SWAP_IN_STATS,
        ResultField.TOTAL_SWAP_INS
    ) to Regex("""total_swapins:\s*(\d+)"""),

    RegexKey(
        CommandType.SWAP_IN_STATS,
        ResultField.SAMPLED_SWAP_INS
    ) to Regex("""sampled_swapins:\s*(\d+)"""),

    RegexKey(
        CommandType.SWAP_IN_STATS,
        ResultField.AVG_SWAP_IN_LAT
    ) to Regex("""avg_ns:\s*(\d+)"""),

    RegexKey(
        CommandType.SWAP_IN_STATS,
        ResultField.P90_SWAP_IN_LAT
    ) to Regex("""p90_ns:\s*(\d+)"""),

    RegexKey(
        CommandType.SWAP_IN_STATS,
        ResultField.P99_SWAP_IN_LAT
    ) to Regex("""p99_ns:\s*(\d+)"""),

    RegexKey(
        CommandType.SWAP_IN_STATS,
        ResultField.MAX_SWAP_IN_LAT
    ) to Regex("""max_ns:\s*(\d+)"""),
)

fun regexFindField(commandType: CommandType, resultField: ResultField, output: String) : String? {
    var regexInput = output
    if (commandType == CommandType.DUMPSYS_THERMALSERVICE) {
        val halSection = Regex(
            """(?ms)^Current temperatures from HAL:\s*\r?\n(.*?)(?=^\S.*:\s*$|\z)"""
        ).find(output)?.groupValues?.get(1).toString()
        regexInput = normalizeThermalZoneNames(halSection)
    }
    val regexKey = RegexKey(commandType, resultField)
    val regex = commandRegexes[regexKey] ?: return null
    return regex
        .find(regexInput)
        ?.groupValues
        ?.getOrNull(1)
}

/**
 * 温区名别名表：先把设备上实际的温区名换成 BIG/MID/LITTLE 这种通用写法，再交给上面的正则匹配。
 *
 * 各 ROM 的温区命名差别很大。当前测试机（EMUI 内核）用的是
 * `cluster0/cluster1/cluster2/gpu/Battery/shell_frame`：
 *   - cluster0 / cluster1 / cluster2 三个 CPU 簇 → LITTLE / MID / BIG
 *   - shell_frame（dumpsys 里 type=SKIN）→ VIRTUAL-SKIN
 *   - 该机没有 soc_therm 温区，所以 socThermTemp 会一直是 0
 *
 * 换机型时，把它对应的温区名加到相应列表里即可；老机型原有名字不受影响。
 */
private val thermalZoneAliases = listOf(
    "LITTLE" to listOf("cluster0"),
    "MID" to listOf("cluster1"),
    "BIG" to listOf("cluster2"),
    "VIRTUAL-SKIN" to listOf("shell_frame"),
)

private fun normalizeThermalZoneNames(section: String): String =
    thermalZoneAliases.fold(section) { text, (canonicalName, deviceNames) ->
        deviceNames.fold(text) { acc, deviceName ->
            acc.replace("mName=$deviceName,", "mName=$canonicalName,")
        }
    }
