# Windows 移植说明与维护指南

> 本文件对应 **main 的新结构（多包分层）** 的移植版本。
> 第一版移植（旧的扁平 `utils/` 布局）保留在本地分支 `win-version`（提交 `5479bdb`），不再维护，仅作历史对照。

## 一、分支与定位

| 引用 | 内容 | 说明 |
| --- | --- | --- |
| `origin/main` | 同事的原始测试脚本（依赖 `/bin/bash` 与 `grep`） | 只读、只拉，不要修改 |
| `win` | 基于 `origin/main` + Windows 移植 | 只在本机使用，**不推送** |
| `main`（本地） | 与 `origin/main` 同步的参考分支 | 用 `git pull --ff-only` 更新 |
| `win-version`（本地） | 旧扁平布局 + 第一版移植 | 历史存档 |

## 二、相对 main 的改动清单

| # | 文件 | 改动 |
| --- | --- | --- |
| 1 | `device/adb/AdbCommands.kt` | `/bin/bash` → `powershell.exe`；root 通路改为 `/eng/system/xbin/su 0 sh`；退出码透传；输出按 UTF-8；失败命令留档 |
| 2 | `device/logcat/LogcatProcess.kt` | `grep --line-buffered -iE` → PowerShell `Select-String`（等价于忽略大小写的整行过滤） |
| 3 | `output/logging/CommandDiagnostics.kt`（新增） | 失败命令、读命令的空输出、解析失败写进 `command.log`，去重并在结尾汇总次数（`logcat -c`、`swapoff` 等静默成功的写命令不记） |
| 4 | `output/logging/Logger.kt` | 每条日志立即 `flush()`，程序中途崩溃也不丢日志 |
| 5 | `metrics/SamplingJob.kt` | 单次采样失败不再终止整个采样线程（前 3 次打堆栈，之后降频提示） |
| 6 | `metrics/MetricsCollector.kt` | vmstat / 温度 / zram mm_stat 解析不出内容时，把原始回显写进 `command.log` |
| 7 | `metrics/parser/ParseZramStat.kt` | 解析到非数字时返回 null，不再抛异常 |
| 8 | `metrics/parser/RegexUtils.kt` | 温度温区名别名（本机是 cluster0/1/2、shell_frame） |
| 9 | `experiment/ExperimentRunner.kt` | `am start` 没回 LaunchState 时留档原始输出（应用没装/组件名不符一眼可见） |
| 10 | `Main.kt` | 挂载诊断输出、结尾打印诊断汇总、零样本时给出提示 |
| 11 | `.gitignore` | 增加 `run.log` / `run-*.log` |
| 12 | `test.ps1`（新增） | Windows 版批跑脚本（对应同事的 `test.sh`） |
| 13 | `gradle/wrapper/gradle-wrapper.properties` | 单独提交：Gradle 发行版改用腾讯镜像（仅本机网络便利，可随时还原） |
| 14 | `device/swap/SwapController.kt`、`cli/AppCommand.kt`、`config/ExperimentConfig.kt` | flash swap 防写死保护：创建文件前检查 `/data` 剩余空间；新增 `-f/--flash-swap-size-mb`（合并 main 后短选项从 `-s` 改为 `-f`，因为 main 的 `-s` 是随机种子）；本地默认值 4096MB → 1024MB |
| 15 | `domain/metrics/SamplingItem.kt`、`metrics/parser/ParseZramStat.kt`、`metrics/MetricsCollector.kt`、`output/csv/CsvWriter.kt` | hyperhold 下刷/回抬统计接入每 10s 采样：新增 `parseHyperholdReport()`（解析 `/sys/block/zram0/hyperhold_report` 的 "hyperhold io stat" 段），`sample.csv` 新增 21 列（含 ReadAmp/WriteAmp、PF 命中率、读写带宽） |

## 三、Windows 上的关键实现细节（都是踩过的坑）

1. **命令原文通过环境变量传递**（`ADB_SHELL_COMMAND` / `ADB_ROOT_COMMAND`），
   PowerShell 不把它当脚本文本解析，`2>/dev/null`、`>`、空格原样到达设备端。
2. **非 root 通路用 `-split` 复现旧行为**：旧版 `adb.exe shell $command` 由 bash 按空白拆词，
   现在 `& adb.exe shell (-split $env:ADB_SHELL_COMMAND)` 拆出的参数个数与之一致。
3. **root 通路不能用 PowerShell 管道**：`$env:X | adb.exe ...` 会给子进程 stdin 自动补 `CRLF`，
   设备端 sh 把 `\r` 当成最后一个参数的一部分（`logcat -c\r` 直接报错）。
   因此改用 .NET `Process` 精确写入“命令 + 单个 LF（UTF-8）”。
4. **必须显式 `exit $LASTEXITCODE`**：PowerShell 默认只返回 0/1，不透传 adb 的退出码；
   adb 本身启动不了时返回 1，而不是假成功。
5. **`[Console]::OutputEncoding = UTF8`**：中文 Windows 默认按 OEM 代码页（936）转码，
   经 PowerShell 转发的输出会乱码。
6. Windows 10/11 自带 PowerShell 5.1，无需额外安装；项目不再依赖 bash 或 grep。

## 四、如何使用

前提：JDK 21、`adb` 在 PATH、手机已开启 USB 调试并取得 root。

```powershell
cd "D:\桌面\NNSS\swap项目\统计任务\android_app_launch_test"

# 单轮：-t 必填；-a 必填；-p 可选（会拼到日志目录名后面）
.\gradlew.bat run --args="-t 1 -a 1 -p only_zram"

# 批量：4 种 swap × 3 组应用
.\test.ps1
.\test.ps1 -SwapType 2 -AppSet 0        # 只跑 flash swap × 轻量应用组
```

参数含义：

| 参数 | 取值 | 说明 |
| --- | --- | --- |
| `-t` | 0/1/2/3 | swap 方案：0=无 swap（关 zram）、1=仅 zRAM、2=flash swap（关 zram + 建 4GB 交换文件）、3=zSwap（在 2 基础上打开 zswap + 挂 debugfs） |
| `-a` | 0/1/2 | 应用组：0=light、1=middle、2=heavy（见 `domain/app/AppCatalog.kt` 的 `appNameSet`） |
| `-p` | 任意字符串 | 可选，拼进日志目录名，例如 `-p flash_swap` |

运行流程（`Main.kt`）：重启手机并等待开机完成 → 按 `-t` 初始化 swap → 启动采样任务与 logcat 抓取 →
跑 `testRoundCount` 轮（每轮遍历应用组里的应用，`am start -W` 测启动，间隔 `launchIntervalMs`）→
停采样 → 统计汇总 → 写 CSV。

输出在 `logs/<时间戳>_<应用组>_<可选后缀>/`：

| 文件 | 内容 |
| --- | --- |
| `summary.txt` | 冷/温/热启动次数、平均启动耗时、lmkdCnt、温度均值、PSI 增量、总运行时长 |
| `launch.log` / `launch.csv` | 每次启动一行：应用、LaunchState、TotalTime/WaitTime、Status |
| `sample.log` / `sample.csv` | 每 `sampleIntervalMs` 一行：meminfo、PSI、vmstat、温度、zRAM/zSwap、hyperhold（下刷/回抬统计） |
| `logcat.log` | 低内存杀手击杀行（行数即 lmkdCnt） |
| `command.log` | 仅在出问题时生成：失败命令、本该有输出却为空的读命令、解析失败内容的原始回显 |

## 五、怎么改测试内容

| 想改什么 | 改哪里 |
| --- | --- |
| 测哪些应用 / 应用组划分 | `domain/app/AppCatalog.kt`：`globalAppInfos`（包名 + 启动组件）与 `appNameSet`（三组名单） |
| 轮数、采样间隔、启动间隔、采集延迟、flash swap 大小 | `config/ExperimentConfig.kt` 的默认值（`DEFAULT_*`） |
| 换机型 / 换 root 方案 | `device/adb/AdbCommands.kt` 的 `ROOT_SHELL_DEVICE_COMMAND`（Magisk 机器写 `shell su -c sh`） |
| 温度温区名 | `metrics/parser/RegexUtils.kt` 的 `thermalZoneAliases` |
| LMK 日志关键字 | `device/logcat/LogcatProcess.kt` 的 `LMK_KEYWORD` |
| 采样项增减 | `metrics/MetricsCollector.kt` + `domain/metrics/SamplingItem.kt` + `output/csv/CsvWriter.kt`（三处同步改） |

核对组件名的小命令：

```powershell
adb shell pm list packages | Select-String "aweme|bili|autonavi"
adb shell cmd package resolve-activity --brief -c android.intent.category.LAUNCHER com.tencent.mm
```

> 注：`LaunchApplicationItem` 里的 `dumpsysGfxInfo*` 与 `dumpsysMemInfoTotalPss` 目前恒为 0
> （同事的重构里去掉了每次启动后的 dumpsys 采集），需要这两个指标要自己在 `ExperimentRunner` 里补回来。

## 六、同事更新 main 后如何同步

```powershell
git fetch origin
git log  --oneline win..origin/main        # 上游新提交
git diff --stat win...origin/main          # 上游改了哪些文件

# 情况 A：只更新了测试脚本（应用列表、配置等）→ 直接取文件，不动你的移植
git checkout origin/main -- app/src/main/kotlin/com/junj/domain/app/AppCatalog.kt
git checkout origin/main -- app/src/main/kotlin/com/junj/config/ExperimentConfig.kt

# 情况 B：改了逻辑代码 → 把上游提交垫到你的移植下面
git switch win
git rebase origin/main                     # 冲突：改文件 → git add → git rebase --continue
                                           # 想反悔：git rebase --abort
```

同步后按顺序验一遍：

1. `.\gradlew.bat --offline compileKotlin`（能编译）；
2. `.\gradlew.bat run --args="-t 1 -a 0"` 跑一小轮；
3. 看 `command.log` 是否为空、`sample.csv` 的温度/vmstat 是否有值、`launch.log` 是否有 LaunchState。

## 七、flash swap 的注意事项（真机可能死机）

2026-10-08 的一次 `-t 2`（flash swap）实测中，手机在 swap 初始化阶段直接死机/重启。当时的运行目录
`logs/20261008_182926_middle_flash_swap/` 里只有 `summary.txt` 一行 `=== Only Flash Swap ===`，
`command.log` 都没生成 —— 说明它停在 `dd` / `chmod` / `mkswap` / `swapon` 这几步。

随后在真机（华为 HBN-AL00 / EMUI，`/data` 为 f2fs、当时剩余 184GB）上逐条手动验证，结论是：

**命令序列本身没问题，问题出在 upstream 选的文件路径 `/data/per_boot/flash.swap`。**

| 手动验证 | 结果 |
| --- | --- |
| `/data/per_boot`：`dd` 256MB → `chmod` → `mkswap` | `mkswap` 时 adb 直接掉线、**手机重启**（`uptime` 归零、`/data/per_boot` 被清空、zram 自动恢复）—— 与自动跑 4GB 时的现象一致 |
| `/data/local/tmp`：`dd` 256MB → `sync` → `mkswap` → `swapon` | 全部 exit=0，`/proc/swaps` 出现 `file` 类型 swap |
| `/data/local/tmp`：按代码顺序 `swapoff zram → dd 1024MB → chmod → mkswap → swapon` | 全部 exit=0；`mkswap` 输出 `Swapspace size: 1048572k`，`/proc/swaps` 显示 `/data/local/tmp/flash.swap file 1048572`，`free -m` 显示 `Swap: 1023MB` |
| `df -Pk /data` | `/dev/block/sdd88 ... Available 193094800KB`（≈184GB），空间充足，**不是"写满 /data"导致的死机** |

也就是说：`/data/per_boot` 是这台机器上特殊的分区目录（每次开机被清空），在那里做 `mkswap` 会触发整机重启；
把 swap 文件放到普通目录即可正常工作。

现在的保护措施：

1. **路径改为 `/data/local/tmp/flash.swap`**（`SwapController.kt` 的 `FLASH_SWAP_FILE`），这是实测可用的路径；
2. `enableFlashSwap()` 在 `dd` 之前会执行 `df -Pk /data`，要求
   `可用空间 >= swap 文件大小 + 512MB`，不满足就直接报错退出（**不会再写死手机**）；
3. `swapon` 之后会检查 `/proc/swaps` 里有没有这个文件，没有就直接报错中止
   （upstream 不检查 mkswap/swapon 的退出码，否则整轮实验会悄悄跑成"没有 swap"）；
4. 默认大小本地改为 1024MB，可用 `-f` 覆盖：`.\gradlew.bat run --args="-t 2 -a 0 -f 1024"`；
5. 运行日志目录名带 `_flash_swap` 后缀，方便回溯。

如果手机又死机了，恢复与清理：

```powershell
# 长按电源键强制重启（或 adb 还能响应时：adb root; adb reboot）
adb devices
adb shell /eng/system/xbin/su 0 df -h /data                        # 看剩余空间
adb shell /eng/system/xbin/su 0 cat /proc/swaps                     # 重启后 zram 自动恢复
adb shell /eng/system/xbin/su 0 ls -lh /data/local/tmp/flash.swap   # 大文件会留在普通目录里
adb shell /eng/system/xbin/su 0 swapoff /data/local/tmp/flash.swap  # 不再需要就关掉并删除
adb shell /eng/system/xbin/su 0 rm -f /data/local/tmp/flash.swap

# 排查当时的 I/O / OOM 线索
adb shell /eng/system/xbin/su 0 dmesg | Select-String "I/O error|mmc|ufs|oom|Out of memory|lowmemorykiller" | Select-Object -Last 30
```

## 八、已知限制（设备侧，非代码问题）

- 本机内核没有 zRAM writeback → `/sys/block/zram0/bd_stat` 不存在，`zramBd*` 恒为 0；
- `/sys/kernel/debug/zswap/*` 只有 `-t 3`（会挂 debugfs 并打开 zswap）时才有数据；
- 本机没有 `soc_therm` 温区 → `socThermTemp` 恒为 0；`gpu`、`Battery` 温度有，但当前 CSV 没有这两列；
- 应用没装或组件名不符时，`LaunchState` 为空并在 `command.log` 留下 `am-start/no-launch-state`。
