抖音固定操作脚本：从推荐首页执行一轮

分工：
指导人员：打开 App、处理启动弹窗、模拟返回直到 XML 判断为首页，再调用动作脚本。
你负责：定制每个 App 的固定操作、验证动作结果、保存运行记录、交付脚本和接口说明。
本脚本每次执行一轮，不负责启动/停止 App、清空数据或返回首页。

当前固定动作：
1. 检查手机亮屏、抖音前台、竖屏、首页推荐标签被选中。
2. 浏览当前推荐内容 3 秒。
3. 向上滑动一次，确认内容切换，浏览 3 秒。
4. 再向上滑动一次，确认内容切换，浏览 3 秒。
5. 保存最终页面和结果。
共浏览 3 条内容，上滑 2 次，停留共 9 秒；检查和截图会增加运行时间。
可能遇到图文推荐。“浏览”表示页面停留，不能证明视频实际播放了几秒。
本轮结束后仍停在推荐内容页，没有搜索、点赞、评论、关注、分享或发布操作。

手工运行：
1. USB 连接手机，亮屏解锁；adb devices 应显示 device。
2. 打开抖音，处理启动弹窗，停在“首页”的“推荐”内容页。
3. PowerShell 执行：

    cd D:\NNSS\ui\douyin
    & 'C:\Users\仲昭阳\AppData\Local\Programs\Python\Python312\python.exe' .\douyin.py --serial 2MN0224119000036

使用已安装 uiautomator2 的 Python。若解释器路径已改变，需要对应调整。

退出码：
0 = PASS：两次内容切换和三次停留都通过 UI 检查。
2 = NOT_AT_HOME：起始状态不符合要求，交给调度程序恢复首页。
1 = FAIL：连接失败或中途操作失败。

每轮证据：D:\NNSS\ui\douyin\results\时间戳\
home_before.png/xml：起始首页。
after_swipe_1.png/xml、after_swipe_2.png/xml：两次切换后的页面。
result.png/xml 或 failure.png/xml：最终现场。
result.json：每步状态、内容标识、用时、错误和证据采集错误。

验证依据：视频区域内可见的作者、内容描述发生变化，并连续两次读取稳定。
不使用播放画面变化判断切换。定位来自当前采集版本；更新 App 后可能需要调整。
若证据保存失败，会记录 evidence_errors；检查该字段后再交付测试记录。
PASS 表示 UI 操作经过验证，不表示测得了启动延迟或存储读写性能。

接入指导人员的 Python 调度程序：

    import sys
    sys.path.insert(0, r"D:\NNSS\ui\douyin")
    from douyin import run

    # device 是已连接的 uiautomator2 设备；此时调度程序已经恢复首页。
    result = run(device)
    print(result["status"], result["output_dir"])

run(device) 每次只执行一轮，返回字典，含 PASS / FAIL / NOT_AT_HOME。
也可以使用 subprocess.run 调用脚本，读取 returncode 判断结果。
调度顺序：启动 App → 恢复首页 → 调用 run(device) → 切换下一个 App。

交付：douyin.py、README.txt、真机成功的一轮 result.json 和截图。
首次真机通过后，再验证第二次调用和一次“切走再回来”的调用。
