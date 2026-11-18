"""Offline contract checks using captured UI and a simulated device."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import douyin


CAPTURES = Path(__file__).resolve().parents[1] / "captures" / "douyin"
CAPTURE_IDS = {
    "home": "20260926-234612-015523",
    "search": "20260926-234830-479942",
    "content": "20260926-234912-279850",
}


def captured_xml(stage):
    return (CAPTURES / stage / CAPTURE_IDS[stage] / "window.xml").read_text(
        encoding="utf-8")


class FakeDevice:
    def __init__(self, xml):
        self.xml = xml
        self.swipes = []
        self.info = {"screenOn": True}
        self.package = douyin.PACKAGE
        self.advance = True

    def app_current(self):
        return {"package": self.package}

    def dump_hierarchy(self):
        return self.xml

    def window_size(self):
        return (1260, 2844)

    def screenshot(self, filename):
        pass

    def swipe(self, *args, **kwargs):
        self.swipes.append((args, kwargs))
        if self.advance:
            root = ET.fromstring(self.xml)
            for node in root.iter("node"):
                if node.get("resource-id") == douyin.PACKAGE + ":id/desc":
                    node.set("text", "Post %d" % len(self.swipes))
            self.xml = ET.tostring(root, encoding="unicode")


class DouyinTests(unittest.TestCase):
    def test_captured_home_identity_excludes_hotspot(self):
        device = FakeDevice(captured_xml("home"))
        douyin.require_home(device)
        identity = douyin.video_identity(device)
        self.assertEqual(len(identity), 0.5)
        self.assertFalse(any(part[1] == "热点" for part in identity))

    def test_nonhome_and_locked_states_send_no_swipes(self):
        for stage in ("search", "content", "home"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as folder:
                device = FakeDevice(captured_xml(stage))
                if stage == "home":
                    device.info["screenOn"] = False
                result = douyin.run(device, folder)
                self.assertEqual(result["status"], "NOT_AT_HOME")
                self.assertFalse(device.swipes)

    def test_each_call_runs_one_fixed_round_and_persists_results(self):
        device = FakeDevice(captured_xml("home"))
        with tempfile.TemporaryDirectory() as folder, patch.object(douyin.time, "sleep"):
            for _ in range(2):
                result = douyin.run(device, folder)
                self.assertEqual(result["status"], "PASS")
                self.assertEqual([step["name"] for step in result["steps"]], [
                    "watch_post_1", "swipe_video_1", "watch_post_2",
                    "swipe_video_2", "watch_post_3"])
                self.assertTrue(all(step["status"] == "PASS" for step in result["steps"]))
                saved = json.loads((Path(result["output_dir"]) / "result.json").read_text(
                    encoding="utf-8"))
                self.assertEqual(saved["status"], "PASS")
            self.assertEqual(len(device.swipes), 4)

    def test_unchanged_post_marks_swipe_failed(self):
        device = FakeDevice(captured_xml("home"))
        device.advance = False
        with tempfile.TemporaryDirectory() as folder, patch.object(douyin.time, "sleep"):
            result = douyin.run(device, folder, timeout=0.02)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(len(device.swipes), 1)
        self.assertEqual(result["steps"][-1]["name"], "swipe_video_1")
        self.assertEqual(result["steps"][-1]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
