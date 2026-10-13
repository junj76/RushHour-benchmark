package com.junj.domain.app

val appNameSet = arrayOf(
    arrayOf(
        "wechat", "weibo", "zhihu", "qqmusic", "dianping",
        "xiecheng", "jd", "meituan", "netdisk", "kuake"
    ),
    arrayOf(
        "wechat", "weibo", "zhihu", "qqmusic", "dianping",
        "xiecheng", "meituan", "netdisk", "kuake", "wps", "doubao", "gdmap",
    ),
    arrayOf(
        "douyin", "kuaishou", "bilibili", "gdmap", "dianping", "jd", "meituan", "xiecheng",
        "wps", "doubao", "qqmusic", "netdisk", "weibo", "wechat", "zhihu", "kuake",
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
