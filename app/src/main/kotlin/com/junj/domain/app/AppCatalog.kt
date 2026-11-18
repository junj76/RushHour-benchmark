package com.junj.domain.app

// 原国内应用集合及启动入口，保留供后续切换。
/*
val appNameSet = arrayOf(
    arrayOf(
        "douyin", "bilibili", "zhihu", "wps", "doubao", "xiecheng",
    ),
    arrayOf(
        "wechat", "weibo", "zhihu", "qqmusic", "dianping",
        "xiecheng", "meituan", "netdisk", "wps", "doubao",
    ),
    arrayOf(
        "douyin", "kuaishou", "bilibili", "gdmap", "jd", "xiecheng",
        "wps", "doubao", "netdisk", "weibo", "wechat", "kuake",
    ),
)

val globalAppInfos = arrayOf(
    ApplicationInfo("douyin", "com.ss.android.ugc.aweme", "com.ss.android.ugc.aweme/.splash.SplashActivity"),
    ApplicationInfo("kuaishou", "com.smile.gifmaker", "com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity"),
    ApplicationInfo("bilibili", "tv.danmaku.bili", "tv.danmaku.bili/.MainActivityV2"),
    ApplicationInfo("gdmap", "com.autonavi.minimap", "com.autonavi.minimap/com.autonavi.map.activity.SplashActivity"),
    ApplicationInfo("dianping", "com.dianping.v1", "com.dianping.v1/.NovaMainActivity"),
    ApplicationInfo("jd", "com.jingdong.app.mall", "com.jingdong.app.mall/.MainFrameActivity"),
    ApplicationInfo("meituan", "com.sankuai.meituan", "com.sankuai.meituan/com.meituan.android.pt.homepage.activity.MainActivity"),
    ApplicationInfo("xiecheng", "ctrip.android.view", "ctrip.android.view/ctrip.business.splash.CtripSplashActivity"),
    ApplicationInfo("wps", "cn.wps.moffice_eng", "cn.wps.moffice_eng/cn.wps.moffice.documentmanager.ab.proxy.main"),
    ApplicationInfo("doubao", "com.larus.nova", "com.larus.nova/com.larus.home.impl.alias.AliasActivity1"),
    ApplicationInfo("qqmusic", "com.tencent.qqmusic", "com.tencent.qqmusic/.activity.AppStarterActivity"),
    ApplicationInfo("netdisk", "com.baidu.netdisk", "com.baidu.netdisk/.ui.DefaultMainActivity"),
    ApplicationInfo("weibo", "com.sina.weibo", "com.sina.weibo/.SplashActivity"),
    ApplicationInfo("wechat", "com.tencent.mm", "com.tencent.mm/.ui.LauncherUI"),
    ApplicationInfo("zhihu", "com.zhihu.android", "com.zhihu.android/.app.ui.activity.MainActivity"),
    ApplicationInfo("kuake", "com.quark.browser", "com.quark.browser/com.ucpro.MainActivity"),
)
*/

// 启动入口来自当前测试手机；空字符串表示装好应用后在启动时查询。
val globalAppInfos = arrayOf(
    ApplicationInfo("youtube_shorts", "com.google.android.youtube", "com.google.android.youtube/.app.honeycomb.Shell\$HomeActivity"),
    ApplicationInfo("youtube", "com.google.android.youtube", "com.google.android.youtube/.app.honeycomb.Shell\$HomeActivity"),
    ApplicationInfo("aliexpress", "com.alibaba.aliexpresshd", "com.alibaba.aliexpresshd/com.aliexpress.app.FirstActivity"),
    ApplicationInfo("booking", "com.booking", "com.booking/.startup.HomeActivity"),
    // 暂未安装，短测先排除，装好后取消注释。
    // ApplicationInfo("chatgpt", "com.openai.chatgpt", ""),
    // 暂时移出测试，保留入口供后续恢复。
    // ApplicationInfo("foodpanda", "com.global.foodpanda.android", "com.global.foodpanda.android/de.foodora.android.ui.launcher.LauncherActivity"),
    ApplicationInfo("github", "com.github.android", "com.github.android/.main.MainActivity"),
    ApplicationInfo("gmail", "com.google.android.gm", "com.google.android.gm/.ConversationListActivityGmail"),
    ApplicationInfo("gmap", "com.google.android.apps.maps", "com.google.android.apps.maps/com.google.android.maps.MapsActivity"),
    ApplicationInfo(
        "google", "com.google.android.googlequicksearchbox", "com.google.android.googlequicksearchbox/.SearchActivity",
        processName = "com.google.android.googlequicksearchbox:googleapp",
    ),
    ApplicationInfo("gtranslate", "com.google.android.apps.translate", "com.google.android.apps.translate/.TranslateActivity"),
    ApplicationInfo("ins", "com.instagram.android", "com.instagram.android/.activity.MainTabActivity"),
    ApplicationInfo("pinterest", "com.pinterest", "com.pinterest/.activity.PinterestActivity"),
    ApplicationInfo("reddit", "com.reddit.frontpage", "com.reddit.frontpage/launcher.default"),
    // ApplicationInfo("spotify", "com.spotify.music", ""),
    // ApplicationInfo("tiktok", "com.zhiliaoapp.musically", ""),
    ApplicationInfo("tripadvisor", "com.tripadvisor.tripadvisor", "com.tripadvisor.tripadvisor/com.tripadvisor.android.ui.launcher.LauncherActivity"),
    ApplicationInfo("twitch", "tv.twitch.android.app", "tv.twitch.android.app/.core.LandingActivity"),
    ApplicationInfo("uber", "com.ubercab", "com.ubercab/.presidio.app.core.root.RootActivity"),
    ApplicationInfo("weather", "de.wetteronline.wetterapp", ""),
    // 保留脚本别名 wiki，实际测试应用为 wikiHow，与 profiles/wiki.json 一致。
    ApplicationInfo("wiki", "com.wikihow.wikihowapp", "com.wikihow.wikihowapp/.MainTabActivity"),
)

// -a N 选取上面列表前 N 项；Shorts 和 YouTube 是同一包名的两个测试场景。
