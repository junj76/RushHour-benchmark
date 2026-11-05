"""Visible control selection and diagnostics shared by the patched flows."""
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET


BASE = Path(__file__).resolve().parent


class Screen:
    def __init__(self, xml, package):
        self.root = ET.fromstring(xml)
        self.package = package
        self.parents = {child: parent for parent in self.root.iter() for child in parent}
        self.nodes = [n for n in self.root.iter("node")
                      if n.get("package") == package and self.visible(n)]

    def visible(self, node):
        current = node
        while current is not None:
            if current.get("visible-to-user") == "false":
                return False
            current = self.parents.get(current)
        box = self.box(node)
        return box[2] > box[0] and box[3] > box[1] and node.get("enabled") != "false"

    @staticmethod
    def box(node):
        values = re.findall(r"-?\d+", node.get("bounds", ""))
        return tuple(map(int, values)) if len(values) == 4 else (0, 0, 0, 0)

    @staticmethod
    def rid(node):
        return node.get("resource-id", "").split(":id/")[-1]

    @staticmethod
    def label(node):
        return node.get("text", "").strip() or node.get("content-desc", "").strip()

    def path(self, node):
        parts = []
        while node is not self.root:
            parent = self.parents[node]
            parts.append("*[%d]" % (list(parent).index(node) + 1))
            node = parent
        return "/" + self.root.tag + "/" + "/".join(reversed(parts))

    def element(self, device, node):

        return device.xpath(self.path(node)).get()

    def clickable(self, node):
        while node is not None and node.get("package") == self.package:
            if node.get("clickable") == "true" and self.visible(node):
                return node
            node = self.parents.get(node)
        return None

    def unique_actions(self, nodes):
        actions = []
        for node in nodes:
            action = self.clickable(node)
            if action is not None and action not in actions:
                actions.append(action)
        return actions

    def descendants(self, node):
        return [n for n in node.iter("node") if n in self.nodes]

    def selected(self, node):
        while node is not None and node.get("package") == self.package:
            if node.get("selected") == "true" or node.get("checked") == "true":
                return True
            node = self.parents.get(node)
        return False

    def home_selected(self):
        return any(self.selected(n) for n in self.nodes
                   if re.fullmatch(r"(?i)(Home|首页|主页)(?:[,， ].*)?", self.label(n)))

    def fingerprint(self, node):
        return tuple((self.rid(n), n.get("text", ""), n.get("content-desc", ""),
                      n.get("bounds", "")) for n in self.descendants(node)
                     if self.rid(n) or self.label(n))


def capture(device, package):
    return Screen(device.dump_hierarchy(compressed=False), package)


def wait_value(check, timeout, message, interval=0.15):
    stop = time.monotonic() + timeout
    while True:
        value = check()
        if value:
            return value
        if time.monotonic() >= stop:
            raise RuntimeError(message)
        time.sleep(interval)


def save_failure(device, app, result):
    if device is None:
        return
    try:
        folder = BASE / "ui_dumps"
        folder.mkdir(exist_ok=True)
        path = folder / (app + "_failure_" + str(time.time_ns()) + ".xml")
        path.write_text(device.dump_hierarchy(compressed=False), encoding="utf-8")
        result["failure_xml"] = str(path)
        print("[%s] failure XML: %s" % (app, path), flush=True)
    except Exception as exc:
        result["failure_xml_error"] = str(exc)


def reddit_search(screen):
    for ids in ({"search_bar_field", "search_bar", "search_button", "action_search", "search_icon"},):
        actions = screen.unique_actions(n for n in screen.nodes if screen.rid(n) in ids)
        if len(actions) == 1:
            return actions[0]
        if len(actions) > 1:
            raise RuntimeError("Multiple Reddit search controls; inspect failure XML")
    actions = screen.unique_actions(n for n in screen.nodes if re.fullmatch(
        r"(?i)(?:Search(?:\s+(?:Reddit|anything))?|搜索(?:\s*Reddit)?)(?:[.…]+)?",
        screen.label(n),
    ))
    if len(actions) > 1:
        raise RuntimeError("Multiple Reddit search controls; inspect failure XML")
    return actions[0] if actions else None


INS_MEDIA = {"carousel_image_media_group", "row_feed_photo", "row_feed_photo_imageview",
             "row_feed_video", "media_group"}


def instagram_feed(screen, configured_id=None):

    if any(screen.rid(n) in {"clips_viewer_view_pager", "clips_viewer_root", "clips_viewer_container"}
           for n in screen.nodes):
        raise RuntimeError("Instagram is in Reels; return to the Home feed first")
    media = [n for n in screen.nodes if screen.rid(n) in INS_MEDIA]
    candidates = []
    for n in screen.nodes:
        left, top, right, bottom = screen.box(n)
        vertical = bottom - top > right - left
        has_media = any(m in list(n.iter()) for m in media)
        known = screen.rid(n) in {"list", "recycler_view", "feed_list", "feed_recycler_view"}
        if configured_id and n.get("resource-id") == configured_id:
            known = True
        if vertical and has_media and (known or n.get("scrollable") == "true"):
            candidates.append(n)
    if not candidates:
        return None

    leaves = [n for n in candidates if not any(m is not n and m in list(n.iter()) for m in candidates)]
    if len(leaves) != 1:
        raise RuntimeError("Multiple Instagram feed containers; inspect failure XML")
    return leaves[0]


def instagram_media(screen, feed):
    matches = [n for n in screen.descendants(feed) if screen.rid(n) in INS_MEDIA]

    matches = [n for n in matches if screen.box(n)[3] - screen.box(n)[1] >= 80]
    if not matches:
        return None
    return min(matches, key=lambda n: (screen.box(n)[1], -(
        (screen.box(n)[2] - screen.box(n)[0]) * (screen.box(n)[3] - screen.box(n)[1]))))


def instagram_post_target(screen, feed):
    """Find the current media and its footer, including flat RecyclerView siblings."""
    media = instagram_media(screen, feed)
    if media is None:
        return None
    nodes = screen.descendants(feed)
    position = nodes.index(media)
    headers = [i for i, n in enumerate(nodes) if screen.rid(n) == "row_feed_profile_header"]
    preceding = [i for i in headers if i < position]
    start = max(preceding) if preceding else position
    end = next((i for i in headers if i > position), len(nodes))

    branch = media
    while screen.parents.get(branch) is not feed and screen.parents.get(branch) is not None:
        branch = screen.parents[branch]
    siblings = list(feed)
    if branch in siblings:
        for sibling in siblings[siblings.index(branch) + 1:]:
            if any(screen.rid(n) in INS_MEDIA for n in sibling.iter("node")):
                if sibling in nodes:
                    end = min(end, nodes.index(sibling))
                break

    identities = set()
    for n in media.iter("node"):
        if screen.rid(n) in INS_MEDIA:
            label = screen.label(n).split(",", 1)[0].split("，", 1)[0].strip()
            if label and not re.fullmatch(r"(?i)(Photo|Video|照片|视频)", label):
                identities.add("media:" + label)
    if preceding:
        label = screen.label(nodes[start])
        if label:
            identities.add("header:" + label)

    scope = nodes[start:end]
    candidates = screen.unique_actions(n for n in scope if (
        screen.rid(n) in {"row_feed_button_like", "like_button"}
        or re.fullmatch(r"(?i)(Like|Unlike|赞|点赞|取消赞|喜欢|取消喜欢)", screen.label(n))))

    candidates = [n for n in candidates if n in scope]
    if len(candidates) > 1:
        raise RuntimeError("Multiple like buttons in the current Instagram post")
    return media, identities, candidates[0] if candidates else None


def like_instagram_post(device, package, timeout, settle_seconds, configured_id=None,
                        clock=time.monotonic, sleep=time.sleep):
    stop = clock() + timeout
    identity = None
    reveals = 0
    while True:
        screen = capture(device, package)
        feed = instagram_feed(screen, configured_id)
        target = instagram_post_target(screen, feed) if feed is not None else None
        if target is None:
            raise RuntimeError("未找到当前帖子的媒体；需要失败 XML")
        media, current_identity, button = target
        if identity is None:
            identity = current_identity
        elif not identity.intersection(current_identity):
            raise RuntimeError("露出点赞按钮时无法确认仍是原帖子，已停止，未点赞其他帖子")

        if button is not None:
            if screen.selected(button) or re.fullmatch(
                r"(?i)(Unlike|取消赞|取消喜欢)", screen.label(button)
            ):
                return {"method": "already_liked_control", "like_verified": True,
                        "reveal_swipes": reveals}
            screen.element(device, button).click()
            sleep(settle_seconds)
            return {"method": "post_like_control", "like_verified": False,
                    "reveal_swipes": reveals}

        if not identity:
            raise RuntimeError("点赞按钮未露出，且帖子没有可核对的身份标识；需要 XML")
        if reveals >= 3 or clock() >= stop:
            raise RuntimeError("小幅滚动后仍未找到当前帖子的点赞控件；需要新的失败 XML")
        screen.element(device, feed).swipe("up", scale=0.25)
        reveals += 1
        sleep(max(0, min(settle_seconds, stop - clock())))
        if clock() >= stop:
            raise RuntimeError("露出点赞控件超时；需要新的失败 XML")


def pinterest_cards(screen):
    # 先确认是首页，避免把详情页的相关推荐当成首页图片。
    home_present = any(
        screen.rid(n) == "home_feed_greeting_header_logotype"
        for n in screen.nodes
    )
    if not home_present:
        return []

    return [
        n for n in screen.nodes
        if screen.rid(n) == "pin_rep_id"
        and n.get("clickable") == "true"
        and any(
            screen.rid(parent) == "recycler_adapter_view"
            for parent in ancestors(screen, n)
        )
    ]


def pinterest_pair(screen):
    cards = pinterest_cards(screen)
    pairs = []
    for left in cards:
        a = screen.box(left)
        for right in cards:
            b = screen.box(right)
            overlap = min(a[3], b[3]) - max(a[1], b[1])
            if a[2] <= b[0] + 4 and overlap > min(a[3] - a[1], b[3] - b[1]) * 0.25:
                pairs.append((max(a[1], b[1]), a[1] + b[1], left, right))
    if not pairs:
        return None
    _, _, left, right = min(pairs, key=lambda p: p[:2])
    return left, right


def pin_identity(screen, card):
    return tuple(screen.label(n) for n in screen.descendants(card) if screen.label(n))


TWITCH_PLAYER_IDS = {"theatre-screen", "mini-player-controls-overlay", "video-player",
                     "video_presenter_container", "minimized_overlay", "player_pane"}


def twitch_overlay(screen):

    return [n for n in screen.nodes if screen.rid(n) in TWITCH_PLAYER_IDS
            or re.fullmatch(r"(?:mini[_-]?player)(?:[_-](?:container|view|overlay|controls))?",
                            screen.rid(n), flags=re.I)]


def twitch_clean_home(screen):
    ids = {screen.rid(n) for n in screen.nodes}
    home = any(screen.rid(n) == "viewer_bottom_nav_home" and screen.selected(n)
               for n in screen.nodes)
    return home and bool(ids & {"feed-list", "feed_item_recycler"}) and not twitch_overlay(screen)


def twitch_close(screen):
    roots = twitch_overlay(screen)
    nodes = [n for root in roots for n in screen.descendants(root)]
    ids = {"mini_player_close", "miniplayer_close", "miniplayer_close_button",
           "minimized_overlay_close", "close_miniplayer", "mini-player-close-button"}
    nodes += [n for n in screen.nodes if screen.rid(n) in ids]
    matches = screen.unique_actions(n for n in nodes if screen.rid(n) in ids or re.fullmatch(
        r"(?i)(?:close|dismiss|关闭|關閉)(?:\s+(?:player|mini.?player|video|播放器|小窗|视频))?",
        screen.label(n)))
    if len(matches) > 1:
        raise RuntimeError("Multiple Twitch player close buttons")
    return matches[0] if matches else None


def shorts_tab(screen):
    tabs = screen.unique_actions(n for n in screen.nodes if re.fullmatch(
        r"(?i)(?:Shorts|短视频|短片)(?:[,， ].*)?", screen.label(n)))

    tabs = [n for n in tabs if any(screen.rid(p) in {
             "pivot_bar", "bottom_bar_container", "bottom_navigation", "bottom_navigation_view"}
             for p in ancestors(screen, n))]
    if len(tabs) > 1:
        raise RuntimeError("Multiple Shorts navigation tabs")
    return tabs[0] if tabs else None


def ensure_youtube_home(device, package, timeout):
    screen = capture(device, package)
    if screen.home_selected() and shorts_viewer(screen) is None:
        return {"method": "already_home", "home_verified": True}

    def home_buttons(s):
        return s.unique_actions(n for n in s.nodes if re.fullmatch(
            r"(?i)(Home|首页|首頁)(?:[,， ].*)?", s.label(n)) and any(
                s.rid(p) in {"pivot_bar", "bottom_bar_container", "bottom_navigation",
                             "bottom_navigation_view"} for p in ancestors(s, n)))

    buttons = home_buttons(screen)
    if not buttons and shorts_viewer(screen) is not None:
        device.press("back")
        time.sleep(0.5)
        screen = capture(device, package)
        if screen.home_selected() and shorts_viewer(screen) is None:
            return {"method": "back_from_shorts", "home_verified": True}
        buttons = home_buttons(screen)
    if len(buttons) != 1:
        raise RuntimeError("未找到唯一的 YouTube 底部首页按钮")
    screen.element(device, buttons[0]).click()

    def ready():
        s = capture(device, package)
        return s.home_selected() and shorts_viewer(s) is None

    wait_value(ready, timeout, "点击首页后未退出 Shorts 或未选中首页")
    return {"method": "home_tab_control", "home_verified": True}


def ancestors(screen, node):
    while node is not None:
        yield node
        node = screen.parents.get(node)


def shorts_viewer(screen):
    ids = {"reel_recycler", "reel_recycler_view", "shorts_recycler_view", "reel_watch_fragment_root",
           "reel_watch_player", "reel_player_page_container", "shorts_player_container"}
    matches = [n for n in screen.nodes if screen.rid(n) in ids]
    if not matches:
        return None
    return max(matches, key=lambda n: (screen.box(n)[2] - screen.box(n)[0]) *
               (screen.box(n)[3] - screen.box(n)[1]))


def shorts_content(screen):

    ids = {"reel_video_title", "reel_title", "shorts_video_title", "reel_channel_name",
           "reel_channel_name_text", "reel_pivot_button"}
    return tuple(sorted((screen.rid(n), screen.label(n)) for n in screen.nodes
                        if screen.rid(n) in ids and screen.label(n)))


def watch_shorts(device, package, deadline, timeout, watch_seconds, clock=time.monotonic,
                 sleep=time.sleep, steps=None):
    if steps is None:
        steps = []
    for index in (1, 2):
        if clock() >= deadline:
            break
        item = {"name": "scroll_next_short_%d" % index, "status": "FAIL"}
        steps.append(item)
        started = clock()
        try:
            screen = capture(device, package)
            viewer = shorts_viewer(screen)
            if viewer is None:
                raise RuntimeError("Shorts viewer disappeared; inspect failure XML")
            # A hierarchy RPC may itself consume the remaining budget.
            if clock() >= deadline:
                steps.pop()
                break
            before = shorts_content(screen)
            screen.element(device, viewer).swipe("up", scale=0.65)
            first_watch_end = clock() + watch_seconds
            changed = False
            stop = min(deadline, clock() + min(timeout, 1.5))
            while clock() < stop:
                after = capture(device, package)
                if shorts_viewer(after) is None:
                    raise RuntimeError("Swipe left the Shorts viewer")
                content = shorts_content(after)
                if before and content and before != content:
                    changed = True
                    break
                sleep(min(0.1, max(0, stop - clock())))
            item.update(status="PASS", detail={"method": "shorts_viewer_control_swipe_up",
                        "video_change_verified": changed, "playback_verified": False})
        except Exception as exc:
            item["error"] = str(exc)
            raise
        finally:
            item["elapsed_seconds"] = round(clock() - started, 3)
        print("[youtube_shorts] scroll_next_short_%d: video_change_verified=%s" %
              (index, changed), flush=True)
        remaining = max(0, deadline - clock())
        duration = min(max(0, first_watch_end - clock()), remaining) if index == 1 else remaining
        sleep(duration)
    remaining = max(0, deadline - clock())
    if remaining:
        sleep(remaining)
    return steps
