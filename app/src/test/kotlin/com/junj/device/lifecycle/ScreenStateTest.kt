package com.junj.device.lifecycle

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** 亮屏判定与失败摘要的单元测试（纯字符串解析，不需要连设备）。 */
class ScreenStateTest {
    private val powerAwake = """
        Power Manager State:
          mWakefulness=Awake
          mWakefulnessChanging=false
          mHoldingDisplaySuspendBlocker=true
    """.trimIndent()

    private val powerAsleep = """
        Power Manager State:
          mWakefulness=Asleep
          mWakefulnessChanging=false
          mHoldingDisplaySuspendBlocker=false
    """.trimIndent()

    private val displayOn = """
        Display Devices: size=1
          mScreenState=ON
          mDisplayState=ON
    """.trimIndent()

    private val displayOff = """
        Display Devices: size=1
          mScreenState=OFF
          mDisplayState=OFF
    """.trimIndent()

    @Test
    fun `screen is on only when both the wakefulness and the display state agree`() {
        assertTrue(isScreenOn(powerAwake, displayOn))
        assertFalse(isScreenOn(powerAwake, displayOff), "power 说醒着但 display 灭着，不算点亮")
        assertFalse(isScreenOn(powerAsleep, displayOn), "display 说 ON 但还没醒，不算点亮")
        assertFalse(isScreenOn(powerAsleep, displayOff))
    }

    @Test
    fun `missing or malformed dumpsys output is treated as screen off`() {
        assertFalse(isScreenOn("", ""))
        assertFalse(isScreenOn("garbage", "garbage"))
        // mWakefulnessChanging 不能被误判成 mWakefulness
        assertFalse(isScreenOn("  mWakefulnessChanging=false", displayOn))
    }

    @Test
    fun `summary reports wakefulness display state and suspend blocker`() {
        val summary = screenStateSummary(powerAsleep, displayOff)
        assertTrue(summary.contains("mWakefulness=Asleep"), summary)
        assertTrue(summary.contains("mScreenState=OFF"), summary)
        assertTrue(summary.contains("mHoldingDisplaySuspendBlocker=false"), summary)
    }

    @Test
    fun `summary degrades gracefully when dumpsys prints nothing useful`() {
        assertEquals("dumpsys reported no power/display state", screenStateSummary("", ""))
    }
}
