"""Bounded application-home recovery, independent of the scenario process."""
import argparse
from contextlib import closing
from http.client import HTTPConnection
import json
from pathlib import Path
import re
import sys
import time

from flow_controls import Screen


HOME_LABEL = r"(?i)(Home|Homepage|\u9996\u9875|\u4e3b\u9875|\u4e3b\u9875\u9762)(?:[,\uff0c ].*)?"


class DeviceNotReady(RuntimeError):
    pass


def matches(node, selector):
    keys = {"resourceId": "resource-id", "description": "content-desc",
            "text": "text", "className": "class", "selected": "selected"}
    for key, expected in selector.items():
        base = key.removesuffix("Matches")
        value = node.get(keys.get(base, base), "")
        if key.endswith("Matches"):
            if re.fullmatch(expected, value) is None:
                return False
        else:
            expected = str(expected).lower() if isinstance(expected, bool) else str(expected)
            if value != expected:
                return False
    return True


def home_visible(app, screen, cfg):
    """Require page controls; foreground package alone never proves home."""
    if not screen.nodes:
        return False
    ids = {screen.rid(n) for n in screen.nodes}
    labels = {screen.label(n) for n in screen.nodes}
    any_selector = lambda items: any(matches(n, s) for s in items for n in screen.nodes)
    selected = screen.home_selected()
    edit = any(n.get("class") == "android.widget.EditText" and n.get("focused") == "true"
               for n in screen.nodes)
    if app in {"youtube", "youtube_shorts"}:
        return ("results" in ids and "pivot_bar" in ids and selected
                and not ids.intersection({"watch_player", "floaty_bar_controls_view",
                                          "modern_miniplayer_close", "reel_watch_player"}))
    if app == "twitch":
        from flow_controls import twitch_clean_home
        return twitch_clean_home(screen)
    if app == "reddit":
        return {"main_top_app_bar_search", "bottom_nav", "feed_lazy_column"} <= ids
    if app == "wiki":
        return "search_button" in ids and "Main Page" in labels and "search_src_text" not in ids
    if app == "booking":
        return ({cfg["destination_id"], cfg["search_id"]} <= ids
                and not ids.intersection({cfg["date_confirm_id"].split(":id/")[-1], cfg["results_id"]}))
    if app == "gmail":
        return any_selector(cfg["selectors"]["home"])
    if app == "gmap":
        return any_selector(cfg["selectors"]["home"]) and not edit
    if app == "github":
        return selected and not edit and any_selector(cfg["selectors"]["home_marker"])
    if app == "uber":
        return (cfg["home_prompt"] in labels and cfg["home_label"] in labels
                and not ids.intersection({"location_editor_bottom_sheet_view", "ub__text_search_v2_scroll_view"}))
    if app == "tripadvisor":
        return {cfg["section_id"], "avatarSearchFieldRoot"} <= ids
    if app == "aliexpress":
        return {"iv_top_logo", "home_tab_layout"} <= ids
    if app == "foodpanda":
        return cfg["manual_label"] in labels
    if app == "pinterest":
        from flow_controls import pinterest_pair
        return selected and bool(pinterest_pair(screen))
    if app == "ins":
        from flow_controls import instagram_feed
        try:
            return selected and instagram_feed(screen) is not None
        except RuntimeError:
            return False
    if app == "spotify":
        return selected and not edit and bool(ids.intersection({"heading_container", "carousel", "home_content"}))
    if app == "google":
        return not edit and (selected or bool(ids.intersection({"search_box", "search_plate"})))
    if app == "gtranslate":
        return not edit and bool(labels.intersection({"\u7ffb\u8bd1\u6587\u5b57", "Translate text", "Enter text"}))
    if app == "tiktok":
        return selected and any(n.get("scrollable") == "true" for n in screen.nodes)
    if app == "chatgpt":
        return any(n.get("class") == "android.widget.EditText" for n in screen.nodes) and bool(labels.intersection({"How can I help you?", "What can I help with?",
                                                 "\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u5fd9\u7684\uff1f"}))
    # Weather must restore its initial scroll position, not just expose its package.
    return False


class Backend:
    def __init__(self, cfg):
        from device_connection import connect_device
        self.device = connect_device()
        self.adb = self.device._dev
        self.cfg = cfg
        self.adb.shell(["input", "keyevent", "224"], timeout=0.8)
        info = self.rpc("deviceInfo", [])
        allowed = cfg.get("packages") or [cfg["package"]]
        stop = time.monotonic() + 2
        while info.get("currentPackageName") not in allowed and time.monotonic() < stop:
            time.sleep(0.2)
            info = self.rpc("deviceInfo", [])
        if not info.get("screenOn") or info.get("currentPackageName") not in allowed:
            raise DeviceNotReady("Unlock the phone and open the target app before testing; current package: "
                                 + str(info.get("currentPackageName")))
        self.cfg["package"] = info["currentPackageName"]

    def rpc(self, method, params):
        # Set the actual ADB tunnel socket timeout, with no restart/retry path.
        import adbutils
        sock = self.adb.create_connection(adbutils.Network.TCP, self.device._device_server_port)
        sock.settimeout(0.65)
        with closing(HTTPConnection("127.0.0.1", timeout=0.65)) as connection:
            connection.sock = sock
            connection.request("POST", "/jsonrpc/0", json.dumps({"jsonrpc": "2.0", "id": 1,
                                                               "method": method, "params": params}),
                               {"Content-Type": "application/json", "Accept-Encoding": ""})
            response = connection.getresponse()
            value = json.loads(response.read())
            if response.status != 200 or value.get("error"):
                raise RuntimeError("Recovery RPC failed: " + str(value))
            return value["result"]

    def screen(self):
        if not self.rpc("deviceInfo", []).get("screenOn"):
            raise DeviceNotReady("Phone screen turned off during the test; unlock before continuing")
        return Screen(self.rpc("dumpWindowHierarchy", [False, 50]), self.cfg["package"])

    def back(self):
        return self.adb.shell(["input", "keyevent", "4"], timeout=0.8)

    def click(self, node):
        selector = {"packageName": self.cfg["package"]}
        for key, attr in (("resourceId", "resource-id"), ("description", "content-desc"), ("text", "text")):
            if node.get(attr):
                selector[key] = node.get(attr)
        if len(selector) == 1:
            return False
        target = self.device(**selector)
        if target.count != 1:
            return False
        target.click(timeout=0.2)
        return True

    def restart(self):
        package = self.cfg["package"]
        self.adb.shell(["am", "force-stop", package], timeout=0.8)
        # Resolve on the phone; never reuse a hard-coded launcher activity.
        text = self.adb.shell(["cmd", "package", "resolve-activity", "--brief", "-a",
                               "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER",
                               package], timeout=0.8)
        components = [line.strip() for line in text.splitlines() if line.strip().startswith(package + "/")]
        if not components:
            raise RuntimeError("No launcher activity for " + package)
        output = self.adb.shell(["am", "start", "-a", "android.intent.action.MAIN", "-c",
                                "android.intent.category.LAUNCHER", "-p", package], timeout=0.8)
        if "Error:" in output or "Exception" in output:
            raise RuntimeError(output)

    def weather_top(self, screen):
        controls = [n for n in screen.nodes if n.get("class") == "android.widget.ScrollView"
                    and n.get("scrollable") == "true"]
        if len(controls) != 1:
            return False
        selector = self.device(packageName=self.cfg["package"], className="android.widget.ScrollView",
                               scrollable=True).selector
        # False means the container cannot scroll farther toward its beginning.
        return self.rpc("scrollBackward", [selector, True, 30]) is False


def recover(backend, app, cfg, budget, normal_budget=3, clock=time.monotonic, pause=time.sleep):
    started = clock()
    stop = started + budget
    result = {"home_verified": False, "restarted": False, "back_count": 0,
              "errors": [], "method": "normal_return_then_restart"}
    last_xml = None
    restarted = False
    revealed = False
    attempted_controls = set()
    while clock() < stop - 0.8:
        try:
            screen = backend.screen()
            last_xml = screen
            weather_top = app == "weather" and backend.weather_top(screen)
            if home_visible(app, screen, cfg) or weather_top:
                result["home_verified"] = True
                break
            if app == "weather" and clock() - started < normal_budget:
                pause(0.1)
                continue
            if app == "chatgpt":
                new_chat = screen.unique_actions(n for n in screen.nodes if re.fullmatch(
                    r"(?i)(New chat|\u65b0\u804a\u5929|\u65b0\u5efa\u804a\u5929)", screen.label(n)))
                if len(new_chat) == 1 and "new_chat" not in attempted_controls:
                    attempted_controls.add("new_chat")
                    backend.click(new_chat[0])
                    pause(0.1)
                    continue
            close_ids = {"modern_miniplayer_close", "mini-player-close-button", "close_button",
                         "miniplayer_close", "player_close_button"}
            close = [n for n in screen.nodes if screen.rid(n) in close_ids]
            if app == "twitch":
                from flow_controls import twitch_close
                button = twitch_close(screen)
                close = [button] if button is not None else []
            if app in {"youtube", "youtube_shorts", "twitch"} and len(close) == 1:
                identity = (screen.rid(close[0]), screen.label(close[0]))
                if identity not in attempted_controls:
                    attempted_controls.add(identity)
                    backend.click(close[0])
                    pause(0.1)
                    continue
            if app == "twitch" and not revealed:
                overlays = [n for n in screen.nodes if re.fullmatch(r"(?i)(Show|Hide) mini player controls",
                                                                   n.get("content-desc", ""))]
                if len(overlays) == 1:
                    revealed = True
                    backend.click(overlays[0])
                    pause(0.1)
                    continue
            from flow_controls import ancestors
            navigation = {"pivot_bar", "bottom_nav", "bottom_navigation", "bottom_navigation_view",
                          "tab_bar", "home_tab_layout"}
            tabs = screen.unique_actions(n for n in screen.nodes
                                         if re.fullmatch(HOME_LABEL, screen.label(n)) and not screen.selected(n)
                                         and any(screen.rid(parent) in navigation for parent in ancestors(screen, n)))
            if len(tabs) == 1:
                identity = (screen.rid(tabs[0]), screen.label(tabs[0]))
                if identity not in attempted_controls:
                    attempted_controls.add(identity)
                    backend.click(tabs[0])
                    pause(0.1)
                    continue
        except DeviceNotReady as exc:
            result["errors"].append(str(exc))
            result["error"] = str(exc)
            break
        except Exception as exc:
            result["errors"].append(str(exc))
        if clock() >= stop:
            break
        if not restarted and (clock() - started >= normal_budget or result["back_count"] >= 3):
            # Set before issuing commands so a timed-out launch is never retried in a loop.
            restarted = True
            result["restarted"] = True
            try:
                backend.restart()
            except Exception as exc:
                result["errors"].append(str(exc))
        elif not restarted:
            try:
                backend.back()
                result["back_count"] += 1
            except Exception as exc:
                result["errors"].append(str(exc))
        pause(min(0.25, max(0, stop - clock())))
    result["return_seconds"] = round(clock() - started, 3)
    if not result["home_verified"]:
        result.setdefault("error", "Application home was not verified within the return budget")
        if last_xml is not None:
            result["visible_ids"] = sorted({last_xml.rid(n) for n in last_xml.nodes if last_xml.rid(n)})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        cfg = json.loads(args.config.read_text(encoding="utf-8-sig"))
        backend = Backend(cfg)
        args.ready.write_text(json.dumps({"ready": True}), encoding="utf-8")
        command = json.loads(sys.stdin.readline())
        result = recover(backend, args.app, cfg, command["budget"])
        args.result.write_text(json.dumps(result), encoding="utf-8")
        return 0 if result["home_verified"] else 1
    except Exception as exc:
        args.result.write_text(json.dumps({"home_verified": False, "error": str(exc)}), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
