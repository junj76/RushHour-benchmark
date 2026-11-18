"""Keep UI selectors while avoiding slow UiAutomation event injection."""
import os
import time


KEYCODES = {"home": 3, "back": 4, "left": 21, "right": 22, "up": 19, "down": 20,
            "center": 23, "menu": 82, "search": 84, "enter": 66, "delete": 67,
            "del": 67, "recent": 187, "recent_apps": 187, "volume_up": 24,
            "volume_down": 25, "volume_mute": 164, "camera": 27, "power": 26}


class SystemInputMixin:
    def _system_input(self, *args, timeout=3):
        started = time.monotonic()
        output = self._dev.shell(["input", *map(str, args)], timeout=timeout)
        if output and any(token in output.lower() for token in ("error", "exception", "usage:")):
            raise RuntimeError("Android input failed: " + output)
        if os.environ.get("ENAPP_TRACE_INPUT") == "1":
            print("[input] %s %.3fs" % (args[0], time.monotonic() - started), flush=True)
        return True

    def click(self, x, y):
        if os.environ.get("ENAPP_STANDARD_INPUT") == "1":
            return super().click(x, y)
        x, y = self.pos_rel2abs(x, y)
        with self._operation_delay("click"):
            self._system_input("tap", int(x), int(y))

    def long_click(self, x, y, duration=0.5):
        if os.environ.get("ENAPP_STANDARD_INPUT") == "1":
            return super().long_click(x, y, duration)
        x, y = self.pos_rel2abs(x, y)
        with self._operation_delay("click"):
            self._system_input("swipe", int(x), int(y), int(x), int(y), int(duration * 1000),
                               timeout=max(3, duration + 1))

    def double_click(self, x, y, duration=0.1):
        if os.environ.get("ENAPP_STANDARD_INPUT") == "1":
            return super().double_click(x, y, duration)
        self.click(x, y)
        time.sleep(duration)
        self.click(x, y)

    def swipe(self, fx, fy, tx, ty, duration=None, steps=None):
        if os.environ.get("ENAPP_STANDARD_INPUT") == "1":
            return super().swipe(fx, fy, tx, ty, duration=duration, steps=steps)
        fx, fy = self.pos_rel2abs(fx, fy)
        tx, ty = self.pos_rel2abs(tx, ty)
        seconds = max(0.01, steps * 0.005 if steps is not None else (duration or 0.275))
        with self._operation_delay("swipe"):
            return self._system_input("swipe", int(fx), int(fy), int(tx), int(ty), int(seconds * 1000),
                                      timeout=max(3, seconds + 1))

    def press(self, key, meta=None):
        if os.environ.get("ENAPP_STANDARD_INPUT") == "1" or meta:
            return super().press(key, meta)
        code = KEYCODES.get(key.lower()) if isinstance(key, str) else key
        if code is None:
            return super().press(key, meta)
        with self._operation_delay("press"):
            return self._system_input("keyevent", code)

    def jsonrpc_call(self, method, params=None, timeout=10):
        if (method != "setText" or os.environ.get("ENAPP_STANDARD_INPUT") == "1"
                or not isinstance(params, (list, tuple)) or len(params) != 2
                or not isinstance(params[0], dict)):
            return super().jsonrpc_call(method, params, timeout)
        selector, text = params
        # setText in the server clicks via UiObject2 before setting text. Avoid that
        # event-injection wait, retaining the selector and exact read-back check.
        if super().jsonrpc_call("count", [selector], timeout) != 1:
            raise RuntimeError("Text input selector must match exactly one control")
        info = super().jsonrpc_call("objInfo", [selector], timeout)
        bounds = info.get("visibleBounds") or info["bounds"]
        if not info.get("focused"):
            self.click((bounds["left"] + bounds["right"]) / 2,
                       (bounds["top"] + bounds["bottom"]) / 2)
        if super().jsonrpc_call("clearTextField", [selector], timeout) is False:
            raise RuntimeError("Failed to clear the selected text input")
        if text:
            super().jsonrpc_call("setClipboard", ["ENapp text input", text], timeout)
            self._system_input("keyevent", 279)
            stop = time.monotonic() + 1
            while True:
                if super().jsonrpc_call("getText", [selector], timeout) == text:
                    return True
                if time.monotonic() >= stop:
                    raise RuntimeError("Text paste did not match the requested value")
                time.sleep(0.05)
        return True
