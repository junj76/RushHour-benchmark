package com.junj.domain.survival

data class AppSurvivalResult(
    val round: Int,
    val launchPosition: Int,
    val appName: String,
    val packageName: String,
    val launchedPid: Long?,
    val pidAtRoundEnd: Long?,
    val originalProcessAlive: Boolean,
    val appCurrentlyRunning: Boolean,
)
