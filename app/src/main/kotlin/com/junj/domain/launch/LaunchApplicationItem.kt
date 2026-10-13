package com.junj.domain.launch

data class LaunchApplicationItem(
    // Milliseconds elapsed since the start of the test run.
    val launchStamp: Long,

    val amStartRound: Int,
    val amStartAppName: String,
    val amStartLaunchState: String,
    val amStartTotalTime: Long,
    val amStartWaitTime: Long,
    val amStartStatus: String,
    val dumpsysGfxInfoJankyFrames: Double,
    val dumpsysGfxInfoP50RenderLat: Int,
    val dumpsysGfxInfoP90RenderLat: Int,
    val dumpsysGfxInfoP95RenderLat: Int,
    val dumpsysGfxInfoP99RenderLat: Int,
    val dumpsysMemInfoTotalPss: Int,
)
