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
        return (bool(ids.intersection({"thread_list_view", "conversation_list_view"}))
                and not ids.intersection({"subject_and_folder_view", "conversation_webview",
                                          "conversation_container", "compose_view"})
                and not any(n.get("class") == "android.webkit.WebView" for n in screen.nodes)
                and "search_view" not in ids)
    if app == "gmap":
        return any_selector(cfg["selectors"]["home"]) and not edit
    if app == "github":
        input_classes = {
            "android.widget.EditText",
            "android.widget.AutoCompleteTextView",
            "android.widget.MultiAutoCompleteTextView",
        }
        search_input_visible = any(
            node.get("class") in input_classes
            for node in screen.nodes
        )
        return (
            selected
            and not search_input_visible
            and any_selector(cfg["selectors"]["home_marker"])
        )
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
        info = self.rpc("deviceInfo", [])
        if not info.get("screenOn"):
            raise DeviceNotReady("Phone screen turned off during the test; unlock before continuing")
        screen = Screen(self.rpc("dumpWindowHierarchy", [False, 50]), self.cfg["package"])
        screen.foreground_package = info.get("currentPackageName")
        return screen

    def back(self):
        return self.adb.shell(["input", "keyevent", "4"], timeout=0.8)

    def click(self, node):
        package = self.cfg["package"]
        class_name = node.get("class", "")
        resource_id = node.get("resource-id", "")
        description = node.get("content-desc", "")
        text = node.get("text", "")

        selector = {"packageName": package}

        if class_name:
            selector["className"] = class_name

        if resource_id:
            selector["resourceId"] = resource_id
        elif description:
            selector["description"] = description
        elif text and class_name != "android.widget.EditText":
            selector["text"] = text

        # EditText 不依赖可能变化的输入文字或占位提示。
        if len(selector) == 1:
            raise RuntimeError("控件缺少可用于定位的属性")

        target = self.device(**selector)
        count = self.rpc("count", [target.selector])
        if count != 1:
            raise RuntimeError(
                "控件二次定位匹配数量为 %s，选择器：%s"
                % (count, json.dumps(selector, ensure_ascii=False))
            )

        info = self.rpc("objInfo", [target.selector])
        if info.get("enabled") is False:
            raise RuntimeError("控件当前不可用")

        box = info.get("visibleBounds") or info.get("bounds")
        if not box or (
            box["right"] <= box["left"]
            or box["bottom"] <= box["top"]
        ):
            raise RuntimeError("控件没有有效的可见范围")

        x = (box["left"] + box["right"]) // 2
        y = (box["top"] + box["bottom"]) // 2

        self.adb.shell(
            ["input", "tap", str(x), str(y)],
            timeout=1.5,
        )
        return True

    def restart(self):
        package = self.cfg["package"]
        # Resolve before stopping: a lookup failure must not leave a working app stopped.
        text = self.adb.shell(["cmd", "package", "resolve-activity", "--brief", "-a",
                               "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER",
                               package], timeout=0.8)
        components = [line.strip() for line in text.splitlines() if line.strip().startswith(package + "/")]
        if not components:
            raise RuntimeError("No launcher activity for " + package)
        self.adb.shell(["am", "force-stop", package], timeout=0.8)
        # Use the resolved component; a package-scoped implicit MAIN intent may not resolve.
        output = self.adb.shell(["am", "start", "-a", "android.intent.action.MAIN", "-c",
                                "android.intent.category.LAUNCHER", "-n", components[-1]], timeout=0.8)
        if "Error:" in output or "Exception" in output:
            raise RuntimeError(output)

    def weather_top(self, screen):
        controls = [n for n in screen.nodes if n.get("class") == "android.widget.ScrollView"
                    and n.get("scrollable") == "true"]
        if len(controls) != 1:
            return False
        selector = self.device(packageName=self.cfg["package"], className="android.widget.ScrollView",
                               scrollable=True).selector

        return self.rpc("scrollBackward", [selector, True, 30]) is False


def recover(backend, app, cfg, budget, normal_budget=3, clock=time.monotonic, pause=time.sleep,
            progress=None):
    if app in {"ins", "twitch", "chatgpt", "github", "weather"}:
        return finish_special_app(
            backend, app, cfg, budget, clock, pause, progress
        )
    started = clock()
    stop = started + budget
    result = {"home_verified": False, "restarted": False, "back_count": 0,
              "errors": [], "method": "normal_return_then_restart"}
    last_xml = None
    restarted = False
    revealed = False
    attempted_controls = set()
    pending_until = started
    result["actions"] = []

    def action(name):
        result["actions"].append({"action": name, "elapsed_seconds": round(clock() - started, 3)})
        if progress is not None:
            progress(result)

    while clock() < stop - 0.8:
        safe_back = False
        try:
            screen = backend.screen()
            last_xml = screen
            safe_back = bool(screen.nodes) and getattr(screen, "foreground_package", screen.package) == screen.package
            weather_top = app == "weather" and backend.weather_top(screen)
            if safe_back and (home_visible(app, screen, cfg) or weather_top):
                result["home_verified"] = True
                action("home_verified")
                break
            if clock() < pending_until:
                pause(0.15)
                continue
            if app == "weather" and clock() - started < normal_budget:
                pause(0.1)
                continue
            if app == "chatgpt":
                new_chat = screen.unique_actions(n for n in screen.nodes if re.fullmatch(
                    r"(?i)(New chat|\u65b0\u804a\u5929|\u65b0\u5efa\u804a\u5929)", screen.label(n)))
                if len(new_chat) == 1 and "new_chat" not in attempted_controls:
                    attempted_controls.add("new_chat")
                    action("new_chat")
                    backend.click(new_chat[0])
                    pending_until = clock() + 0.6
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
                    action("close_player")
                    backend.click(close[0])
                    pending_until = clock() + 0.8
                    continue
            if app == "twitch" and not revealed:
                overlays = [n for n in screen.nodes if re.fullmatch(r"(?i)(Show|Hide) mini player controls",
                                                                   n.get("content-desc", ""))]
                if len(overlays) == 1:
                    revealed = True
                    action("show_player_controls")
                    backend.click(overlays[0])
                    pending_until = clock() + 0.4
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
                    action("home_tab")
                    backend.click(tabs[0])
                    pending_until = clock() + 0.6
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
            restarted = True
            result["restarted"] = True
            action("restart")
            try:
                backend.restart()
                pending_until = clock() + 0.8
            except Exception as exc:
                result["errors"].append(str(exc))
        elif not restarted and safe_back:
            try:
                action("back")
                backend.back()
                result["back_count"] += 1
                pending_until = clock() + 0.7
            except Exception as exc:
                result["errors"].append(str(exc))
        pause(min(0.25, max(0, stop - clock())))
    result["return_seconds"] = round(clock() - started, 3)
    if not result["home_verified"]:
        result.setdefault("error", "Application home was not verified within the return budget")
        if last_xml is not None:
            result["visible_ids"] = sorted({last_xml.rid(n) for n in last_xml.nodes if last_xml.rid(n)})
    return result

def finish_special_app(backend, app, cfg, budget, clock, pause, progress):
    from flow_controls import (
        instagram_feed,
        twitch_clean_home,
        twitch_close,
        twitch_overlay,
    )

    started = clock()
    deadline = started + budget
    result = {
        "home_verified": False,
        "restarted": False,
        "back_count": 0,
        "errors": [],
        "actions": [],
        "method": "app_specific_final_action",
    }
    back_sent = False
    revealed = False
    clicked_close = False
    final_sent = False
    confirm_after = started

    def record(name):
        result["actions"].append({
            "action": name,
            "elapsed_seconds": round(clock() - started, 3),
        })
        if progress:
            progress(result)

    while clock() < deadline - 0.8:
        try:
            screen = backend.screen()
            foreground = getattr(screen, "foreground_package", None)
            if foreground != cfg["package"] or not screen.nodes:
                raise RuntimeError(
                    "目标应用不在前台；停止操作，避免返回手机桌面"
                )

            if clock() < confirm_after:
                pause(0.15)
                continue

            if app == "weather":
                controls = [
                    n for n in screen.nodes
                    if n.get("class") == "android.widget.ScrollView"
                    and n.get("scrollable") == "true"
                ]
                if len(controls) != 1:
                    result["error"] = "天气滚动区域未唯一识别"
                    break

                if not final_sent:
                    left, top, right, bottom = screen.box(controls[0])
                    if right <= left or bottom <= top:
                        result["error"] = "天气滚动区域边界无效"
                        break

                    x = (left + right) // 2
                    y1 = int(top + (bottom - top) * 0.8)
                    y2 = int(top + (bottom - top) * 0.2)

                    try:
                        backend.adb.shell(
                            [
                                "input", "swipe",
                                str(x), str(y2),
                                str(x), str(y1), "250",
                            ],
                            timeout=1.5,
                        )
                    except Exception as exc:
                        result["error"] = (
                            "最终滑动未确认完成，停止重试：%s" % exc
                        )
                        break

                    final_sent = True
                    result["last_swipe_executed"] = True
                    record("weather_final_swipe_up")
                    confirm_after = clock() + 0.3
                    continue

                result["home_verified"] = True
                result["home_definition"] = "weather_scroll_page"
                result["position_verified"] = False
                record("weather_page_verified")
                break

            if app == "github":
                def github_home_visible(current):
                    nodes = current.nodes

                    has_home_heading = any(
                        n.get("class") == "android.widget.TextView"
                        and n.get("text", "").strip() in {"主页", "Home"}
                        for n in nodes
                    )
                    has_home_content = any(
                        current.rid(n) == "title"
                        and n.get("text", "").strip()
                        in {"我的工作", "My Work", "My work"}
                        for n in nodes
                    )
                    has_search_input = any(
                        current.rid(n) in {
                            "search_src_text",
                            "search_close_btn",
                        }
                        for n in nodes
                    )
                    has_back_button = any(
                        n.get("class") == "android.widget.ImageButton"
                        and n.get("content-desc", "").strip().lower()
                        in {"返回", "back", "navigate up"}
                        for n in nodes
                    )

                    return (
                        getattr(current, "foreground_package", None)
                        == cfg["package"]
                        and has_home_heading
                        and has_home_content
                        and not has_search_input
                        and not has_back_button
                    )

                if github_home_visible(screen):
                    pause(0.25)
                    confirmed = backend.screen()
                    if github_home_visible(confirmed):
                        result["home_verified"] = True
                        record("github_home_verified")
                        break
                    confirm_after = clock() + 0.2
                    continue

                if result["back_count"] >= 5:
                    result["error"] = (
                        "已执行五次返回，但仍未确认 GitHub 首页；停止继续返回"
                    )
                    break

                backend.back()
                result["back_count"] += 1
                record("github_back_%d" % result["back_count"])
                print(
                    "[github] 已发送第 %d 次返回"
                    % result["back_count"],
                    flush=True,
                )
                confirm_after = clock() + 0.5
                continue

            if app == "chatgpt":
                fields = [
                    node for node in screen.nodes
                    if node.get("class") == "android.widget.EditText"
                    and node.get("enabled") != "false"
                ]
                if len(fields) != 1:
                    raise RuntimeError("消息输入框不存在或匹配不唯一")

                if not final_sent:
                    record("focus_message_input")
                    if not backend.click(fields[0]):
                        raise RuntimeError("无法唯一定位消息输入框")
                    final_sent = True
                    confirm_after = clock() + 0.3
                    continue

                result["home_verified"] = True
                result["home_definition"] = "current_conversation_input_ready"
                result["conversation_preserved"] = True
                record("conversation_input_verified")
                break

            if app == "ins":
                feed = instagram_feed(
                    screen,
                    cfg["selectors"]["feed"].get("resourceId"),
                )
                if feed is None:
                    raise RuntimeError("Instagram 首页内容流不存在")

                if not final_sent:
                    left, top, right, bottom = screen.box(feed)
                    if right <= left or bottom <= top:
                        raise RuntimeError("内容流可见范围无效")

                    x = (left + right) // 2
                    y1 = int(top + (bottom - top) * 0.15)
                    y2 = int(top + (bottom - top) * 0.85)
                    milliseconds = max(
                        50, int(cfg["gestures"]["scroll_steps"] * 5)
                    )

                    record("final_browse_up")
                    backend.adb.shell(
                        [
                            "input", "swipe",
                            str(x), str(y1), str(x), str(y2),
                            str(milliseconds),
                        ],
                        timeout=1.5,
                    )
                    final_sent = True
                    confirm_after = clock() + 0.35
                    continue

                result["home_verified"] = True
                result["last_swipe_executed"] = True
                result["scroll_verified"] = False
                result["home_definition"] = "instagram_home_feed"
                record("home_feed_verified")
                break

            # Twitch：连续两次确认首页没有播放器，避免动画中的暂态。
            if twitch_clean_home(screen):
                pause(0.25)
                confirmed = backend.screen()
                if (
                    confirmed.foreground_package == cfg["package"]
                    and twitch_clean_home(confirmed)
                ):
                    result["home_verified"] = True
                    result["miniplayer_closed"] = True
                    record("clean_home_verified")
                    break
                continue

            # 当前 Twitch 版本的小窗关闭按钮。
            dismiss_buttons = [
                node for node in screen.nodes
                if screen.rid(node) == "mini-player-dismiss"
                and node.get("enabled") != "false"
            ]

            if len(dismiss_buttons) > 1:
                raise RuntimeError("匹配到多个小窗关闭按钮")

            close = (
                dismiss_buttons[0]
                if dismiss_buttons
                else twitch_close(screen)
            )
            if close is not None:
                if not clicked_close:
                    record("close_miniplayer")
                    if not backend.click(close):
                        raise RuntimeError("小窗关闭按钮匹配不唯一")
                    clicked_close = True
                    confirm_after = clock() + 0.8
                else:
                    pause(0.15)
                continue

            ids = {screen.rid(node) for node in screen.nodes}
            feed_visible = bool(
                ids & {"feed-list", "feed_item_recycler"}
            )

            overlays = [
                node for node in screen.nodes
                if re.fullmatch(
                    r"(?i)(Show|Hide) mini player controls",
                    node.get("content-desc", ""),
                )
            ]
            if feed_visible and len(overlays) == 1 and not revealed:
                record("show_miniplayer_controls")
                if not backend.click(overlays[0]):
                    raise RuntimeError("小窗控制层匹配不唯一")
                revealed = True
                confirm_after = clock() + 0.4
                continue

            # 已经出现小窗时，只处理小窗，不能再按返回。
            mini_ids = {
                "mini-player-controls-overlay",
                "mini_player_controls",
                "miniplayer_controls",
                "minimized_overlay",
            }
            mini_visible = (
                bool(ids & mini_ids)
                or bool(overlays)
                or any(
                    re.search(
                        r"(?i)mini[_-]?player|minimized_overlay",
                        screen.rid(node),
                    )
                    for node in screen.nodes
                )
            )

            # 首页已在上面检查；关闭按钮、控制层也已优先处理。
            # 其余页面最多返回一次，不要求匹配旧版播放器 ID。
            if not back_sent and not mini_visible:
                record("back_to_feed")
                backend.back()
                back_sent = True
                result["back_count"] += 1
                confirm_after = clock() + 0.8
                continue

            # 返回后只等首页或小窗控件，不追加 Back、不重启。
            result["last_visible_ids"] = sorted(
                rid for rid in ids if rid
            )
            result["miniplayer_detected"] = mini_visible
            if progress:
                progress(result)

            pause(0.15)

        except DeviceNotReady as exc:
            result["errors"].append(str(exc))
            break
        except Exception as exc:
            result["errors"].append(str(exc))
            if "目标应用不在前台" in str(exc):
                break
            pause(0.15)

    result["return_seconds"] = round(clock() - started, 3)
    if not result["home_verified"]:
        result.setdefault(
            "error",
            "最终操作或页面验证未完成；未追加 Back，也未重启应用",
        )
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
        def progress(result):
            temporary = args.result.with_suffix(".tmp")
            temporary.write_text(json.dumps({**result, "in_progress": True}), encoding="utf-8")
            temporary.replace(args.result)
        result = recover(backend, args.app, cfg, command["budget"], progress=progress)
        args.result.write_text(json.dumps(result), encoding="utf-8")
        return 0 if result["home_verified"] else 1
    except Exception as exc:
        args.result.write_text(json.dumps({"home_verified": False, "error": str(exc)}), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
