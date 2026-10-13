package com.junj.output

import java.io.File

data class ExperimentOutputPaths(val directory: File) {
    val sampleLog: File get() = File(directory, "sample.log")
    val launchLog: File get() = File(directory, "launch.log")
    val sampleCsv: File get() = File(directory, "sample.csv")
    val launchCsv: File get() = File(directory, "launch.csv")
    val survivalCsv: File get() = File(directory, "survival.csv")
    val summary: File get() = File(directory, "summary.txt")
    val logcat: File get() = File(directory, "logcat.log")

    fun create() {
        directory.mkdirs()
        listOf(sampleLog, launchLog, sampleCsv, launchCsv, survivalCsv, summary)
            .forEach { it.createNewFile() }
    }
}
