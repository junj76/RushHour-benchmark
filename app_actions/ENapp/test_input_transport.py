import contextlib
import os
import unittest
from unittest.mock import Mock, patch

from input_transport import SystemInputMixin


class Base:
    def __init__(self):
        self._dev = Mock()
        self._dev.shell.return_value = ""
        self.calls = []
        self.count = 1
        self.expected_text = ""

    def pos_rel2abs(self, x, y):
        return x, y

    def _operation_delay(self, name):
        return contextlib.nullcontext()

    def click(self, x, y):
        self.calls.append(("standard_click", [x, y]))

    def jsonrpc_call(self, method, params=None, timeout=10):
        self.calls.append((method, params))
        if method == "count":
            return self.count
        if method == "objInfo":
            return {"focused": False, "bounds": {"left": 20, "right": 100, "top": 30, "bottom": 90}}
        if method == "getText":
            return self.expected_text
        if method == "setClipboard":
            self.expected_text = params[1]
        return None


class Device(SystemInputMixin, Base):
    pass


class InputTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ENAPP_STANDARD_INPUT": "0", "ENAPP_TRACE_INPUT": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_control_text_uses_bounds_and_checks_exact_unicode_value(self):
        device = Device()
        selector = {"resourceId": "app:id/text"}
        value = "\u9ec4\u9e64\u697c"
        self.assertTrue(device.jsonrpc_call("setText", [selector, value]))
        self.assertIn(("clearTextField", [selector]), device.calls)
        self.assertIn(("getText", [selector]), device.calls)
        self.assertIn(("setClipboard", ["ENapp text input", value]), device.calls)
        device._dev.shell.assert_any_call(["input", "tap", "60", "60"], timeout=3)
        device._dev.shell.assert_any_call(["input", "keyevent", "279"], timeout=3)
        self.assertFalse(any(method == 'setText' for method, _ in device.calls))

    def test_ambiguous_input_never_taps_or_clears(self):
        device = Device()
        device.count = 2
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            device.jsonrpc_call("setText", [{"text": "shared"}, "value"])
        device._dev.shell.assert_not_called()
        self.assertEqual([method for method, _ in device.calls], ['count'])

    def test_swipe_preserves_steps_duration(self):
        device = Device()
        device.swipe(10, 100, 10, 20, steps=40)
        device._dev.shell.assert_called_once_with(['input', 'swipe', '10', '100', '10', '20', '200'], timeout=3)

    def test_keyboard_return_uses_system_keyevent(self):
        device = Device()
        device.press('back')
        device._dev.shell.assert_called_once_with(['input', 'keyevent', '4'], timeout=3)

    def test_system_input_error_is_not_success(self):
        device = Device()
        device._dev.shell.return_value = 'Error: input denied'
        with self.assertRaises(RuntimeError):
            device.click(10, 20)

    def test_standard_input_optout_is_preserved(self):
        device = Device()
        with patch.dict(os.environ, {'ENAPP_STANDARD_INPUT': '1'}):
            device.click(10, 20)
            device.jsonrpc_call('setText', [{'resourceId': 'field'}, 'value'])
        self.assertEqual([method for method, _ in device.calls], ['standard_click', 'setText'])
        device._dev.shell.assert_not_called()


if __name__ == '__main__':
    unittest.main()
