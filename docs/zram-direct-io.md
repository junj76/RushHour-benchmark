# type=4 自建 zRAM backing device 下刷失败：direct I/O

## 根因

默认 Android backing loop 使用 `dio=1` 和 4096-byte logical block size；旧代码的
`losetup DEVICE FILE` 则是 `dio=0`、512 bytes。后者走 buffered write 路径，设备上出现：

```text
avc: denied { write } for comm="kworker/u16:5"
path="/data/per_boot/zram_backing"
scontext=u:r:kernel:s0 tcontext=u:object_r:per_boot_file:s0
```

这不是 bd_stat 解析错误，也不是 writeback 配额耗尽。原生和自建后端均可使用
`per_boot_file` 标签，差别在 loop I/O 模式。Android 14 设备没有 `swapfile` 类型，不能
用该标签修复，更不需要 `setenforce 0` 或添加 SELinux allow 规则。

参考：[Android 14 fs_mgr loop_control.cpp](https://raw.githubusercontent.com/aosp-mirror/platform_system_core/android-14.0.0_r75/fs_mgr/libdm/loop_control.cpp)。
`EnableDirectIo` 依次调用 `LOOP_SET_BLOCK_SIZE(4096)`、`LOOP_SET_DIRECT_IO(1)`。

## 修复

- [初始化](../app/src/main/kotlin/com/junj/device/swap/ZramWriteback.kt)：loop attach 后、
  写入 backing_dev 前设置 direct I/O，并验证 sysfs。每个初始化命令失败立即停止。
- [helper 部署和校验](../app/src/main/kotlin/com/junj/device/swap/ZramLoopDirectIo.kt)：
  从资源部署到设备 root 创建的随机私有目录，执行后清理。复用旧后端时也检查并修复配置。
- [ARM64 helper 源码](../tools/zram-loop-direct-io-arm64.S)：无 libc/NDK 依赖，
  源码中包含重建命令。目前仅支持 aarch64，重建前先检查架构，避免先 reset 后才发现不支持。
- [下刷任务](../app/src/main/kotlin/com/junj/device/swap/ZramWritebackJob.kt)：idle 失败不继续下刷；
  失败时打印 backing、limit、文件标签和内核 AVC。

## 实机验证

在独立的 zram1 上创建 32 MiB 后端，写入 4 MiB 随机数据，不 reset 系统 zram0。
先以 buffered loop 复现失败，再在**同一个已经绑定的 loop** 上启用 direct I/O。
SELinux 全程 Enforcing，标签和策略均未更改。

| 检查 | buffered | direct I/O |
|---|---:|---:|
| dio / logical_block_size | 0 / 512 | 1 / 4096 |
| writeback exit | 1 | 0 |
| bd_stat（下刷后） | 0 0 0 | 1024 0 1024 |
| bd_stat（回读后） | — | 1024 1024 1024 |

随机数据 SHA-256 写前与回读后一致。bd_stat 的单位是 4 KiB，1024 对应 4 MiB。
`bdReads` 只有真正从后端读取数据后才增长，不要求每次 writeback 时同步增长。

可重复运行应用资源部署 + 独立设备集成测试：

```bash
RUSHHOUR_ZRAM_DEVICE_TEST=1 ./gradlew :app:test \
  --tests com.junj.device.swap.ZramWritebackTest \
  --tests com.junj.device.swap.ZramWritebackDeviceTest
```

需要 adb.exe 可用、已连接 root Android arm64 设备和 zram-control hot_add/hot_remove。
测试会临时创建设备/loop/32 MiB 文件，并在结束时清理；正常单测不会自动触碰设备。
底层复现脚本：[verify-zram-direct-io.sh](../tools/verify-zram-direct-io.sh)。

重新构建并运行原来的 `-t 4` 命令即可。初始化应输出：

```text
zRAM backing loop verified: /dev/block/loopN dio=1 blockSize=4096
```


## 后端扩容时的 AUTOCLEAR

系统原生 backing loop 带 `LO_FLAGS_AUTOCLEAR`。swapoff 后 zram reset 释放最后的设备引用，
loop 会自动解绑。此时再次 `losetup -d` 返回 ENXIO，并不意味着旧后端仍被占用。

扩容流程已改为：reset 后检查绑定是否仍指向预期文件；只有仍绑定时才 detach，
detach 后再次确认 backing_file 已消失或为空，才删除旧文件。若 loop 已被其它文件复用，
拒绝解绑，也不删除文件。节点缺失时按 sysfs 的实际 major:minor 创建，不能猜 minor 编号。

重建前把原逻辑容量保存在同一启动周期的 `/data/per_boot/rushhour_zram_disksize`。
发生初始化错误且 swap 未启用时，尽可能恢复 plain zram，保留原异常；意外中断后若
设备 disksize=0，可从该记录恢复。没有有效记录时拒绝猜容量，应重启恢复原生配置再重试。

**有破坏性、必须显式启用的实机扩容回归**（操作系统 zram0，结束保留 4 GiB 后端）：

```bash
RUSHHOUR_ZRAM_RESIZE_DEVICE_TEST=1 ./gradlew :app:test \
  --tests com.junj.device.swap.ZramWritebackDeviceTest
```

该测试先配 1 GiB 后端，再设置 AUTOCLEAR，执行 1 GiB → 4 GiB 重建，并验证下一次可直接复用。
测试专用 flag helper 源码是 [zram-loop-autoclear-arm64.S](../tools/zram-loop-autoclear-arm64.S)，
它保留 loop 现有配置，仅添加 AUTOCLEAR 标志；不随生产程序打包。

下刷失败诊断也已修正：通过 dd 获取 sysfs 写入 errno；读当前 backing_dev 追溯真实文件和容量；
仅展示本 tick 起点之后捕获的 zram/swap 内核消息，不再把历史对照测试 AVC 当成当前失败。
