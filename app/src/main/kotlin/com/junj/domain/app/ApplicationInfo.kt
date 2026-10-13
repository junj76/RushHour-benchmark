package com.junj.domain.app

data class ApplicationInfo(
    val name: String,
    val packageName: String,
    val componentName: String
)

enum class AppSetType {
    LIGHT,
    MIDDLE,
    HEAVY;

    val code: Int
        get() = ordinal
}

