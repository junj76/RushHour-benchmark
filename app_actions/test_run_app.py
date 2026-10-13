"""Offline tests for ambiguous controls, page checks and blocked scenarios."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import run_app

PKG = "test.app"


def xml(nodes):
    root = ET.Element("hierarchy")
    for attrs in nodes:
        defaults = {"package": PKG, "enabled": "true", "visible-to-user": "true",
                    "bounds": "[10,300][300,400]", "clickable": "true"}
        defaults.update(attrs)
        ET.SubElement(root, "node", defaults)
    return ET.tostring(root, encoding="unicode")


class Device:
    def __init__(self, screen):
        self.screen, self.clicks = screen, []
        self.info = {"screenOn": True}

    def dump_hierarchy(self, **kwargs):
        return self.screen

    def app_current(self):
        return {"package": PKG}

    def window_size(self):
        return (1260, 2844)

    def click(self, x, y):
        self.clicks.append((x, y))

    def screenshot(self, path):
        pass

    def __call__(self, **selector):
        device = self
        class Control:
            count = 1

            def set_text(self, value):
                tree = ET.fromstring(device.screen)
                for node in tree.iter("node"):
                    if node.get("resource-id") == selector.get("resourceId"):
                        node.set("text", value)
                device.screen = ET.tostring(tree, encoding="unicode")
        return Control()


class RunnerTests(unittest.TestCase):
    def scenario(self, nodes):
        self.device = Device(xml(nodes))
        return run_app.Scenario(self.device, {"package": PKG}, Path("."), timeout=0)

    def test_ambiguous_control_stops_before_click(self):
        s = self.scenario([{"text": "搜索"}, {"text": "搜索", "bounds": "[500,300][800,400]"}])
        with self.assertRaises(RuntimeError):
            s.click({"selectors": [{"text": "搜索"}]})
        self.assertEqual(self.device.clicks, [])

    def test_unique_fallback_used_when_first_selector_is_ambiguous(self):
        s = self.scenario([{"text": "搜索", "resource-id": "entry"},
                           {"text": "搜索", "bounds": "[500,300][800,400]"}])
        s.click({"selectors": [{"text": "搜索"}, {"resourceId": "entry"}]})
        self.assertEqual(len(self.device.clicks), 1)

    def test_first_match_order_excludes_search_input(self):
        s = self.scenario([{"text": "咖啡", "bounds": "[10,10][100,80]"},
                           {"text": "咖啡乙", "bounds": "[10,600][400,700]"},
                           {"text": "咖啡甲", "bounds": "[10,350][400,450]"}])
        node = s.find([{"textContains": "咖啡", "minYRatio": 0.1}], first=True)
        self.assertEqual(node.get("text"), "咖啡甲")

    def test_click_requires_expected_page(self):
        s = self.scenario([{"text": "目标"}])
        def navigate(x, y):
            self.device.clicks.append((x, y))
            self.device.screen = xml([{"text": "其他页面"}])
        self.device.click = navigate
        with self.assertRaises(RuntimeError):
            s.execute({"action": "click", "selectors": [{"text": "目标"}],
                       "expect": [[{"text": "详情"}]]})
        self.assertEqual(len(self.device.clicks), 1)

    def test_noop_click_cannot_pass_existing_page_marker(self):
        s = self.scenario([{"text": "目标"}])
        with self.assertRaisesRegex(RuntimeError, "UI state did not change"):
            s.execute({"action": "click", "selectors": [{"text": "目标"}],
                       "expect": [[{"text": "目标"}]]})

    def test_unconfigured_step_blocks_entire_scenario(self):
        profile = {"package": PKG, "home": [[{"text": "首页"}]], "steps": [
            {"name": "first", "action": "click", "selectors": [{"text": "首页"}],
             "expect": [[{"text": "详情"}]]},
            {"name": "unconfigured", "action": "click", "selectors": [],
             "expect": [[{"text": "预览"}]]}]}
        device = Device(xml([{"text": "首页"}]))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            result = run_app.run(device, "test", tmp, profile_path=path)
            self.assertEqual(result["status"], "NEEDS_CONFIGURATION")
            self.assertFalse(device.clicks)

    def test_wrong_home_stops_before_actions(self):
        profile = {"package": PKG, "home": [[{"text": "首页"}]],
                   "steps": [{"name": "view", "action": "wait"}]}
        device = Device(xml([{"text": "详情"}]))
        with tempfile.TemporaryDirectory() as tmp, patch.object(run_app.time, "sleep"):
            path = Path(tmp) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            result = run_app.run(device, "test", tmp, profile_path=path)
            self.assertEqual(result["status"], "NOT_AT_HOME")
            self.assertFalse(device.clicks)

    def test_input_verification_accepts_matching_leaf_node(self):
        s = self.scenario([{"class": "android.widget.EditText", "text": "",
                           "resource-id": "search_input"}])
        detail = s.execute({"action": "input", "selectors": [{"resourceId": "search_input"}],
                            "value": "科普"})
        self.assertEqual(detail, {"value": "科普"})
        self.assertEqual(s.find([{"resourceId": "search_input"}]).get("text"), "科普")

    def test_input_verification_is_scoped_to_original_input(self):
        s = self.scenario([{"class": "android.widget.EditText", "text": "",
                           "resource-id": "search_input"},
                          {"class": "android.widget.EditText", "text": "科普",
                           "resource-id": "other_input", "bounds": "[10,600][300,700]"}])
        detail = s.execute({"action": "input", "selectors": [{"resourceId": "search_input"}],
                            "value": "科普"})
        self.assertEqual(detail, {"value": "科普"})

    def test_bilibili_result_title_need_not_contain_keyword(self):
        package = "tv.danmaku.bili"
        root = ET.fromstring(xml([]))
        def add(parent, resource_id, text, area, clickable=False):
            return ET.SubElement(parent, "node", {
                "package": package, "resource-id": package + ":id/" + resource_id,
                "class": "android.widget.TextView", "text": text,
                "bounds": area, "clickable": str(clickable).lower()})
        add(root, "search_fake_text", "科普", "[217,173][922,274]")
        add(root, "tab_title", "综合", "[0,308][190,443]")
        add(root, "title", "科普", "[0,450][200,500]")
        listing = add(root, "recycler_view", "", "[0,578][1260,2844]")
        card = add(listing, "", "", "[0,578][1260,987]", True)
        title = "6万字3小时：宇宙万物的终极指南"
        add(card, "title", title, "[649,619][1219,743]")
        device = Device(ET.tostring(root, encoding="unicode"))
        device.app_current = lambda: {"package": package}
        profile = json.loads((run_app.ROOT / "profiles" / "bilibili.json").read_text(
            encoding="utf-8"))
        s = run_app.Scenario(device, profile, Path("."), timeout=0)
        s.expect(profile["steps"][2]["expect"])
        detail = s.click(profile["steps"][3])
        self.assertEqual(detail["text"], title)
        self.assertEqual(device.clicks, [(630, 782)])
        self.assertEqual(detail["bounds"], "[0,578][1260,987]")


if __name__ == "__main__":
    unittest.main()
