# 按数量配置负载

`-a N` / `--apps N` 现在表示选取 `AppCatalog.kt` 中前 N 个测试项，不再是轻、中、重的编号。当前允许 1～17；长测遍历 10～17。

列表第一项为 `youtube_shorts`，第二项为 `youtube`。数量递增时保留之前的集合并增加一项。选取集合后仍按 seed 随机排序，每轮结束反转顺序，因此列表顺序不保证实际启动顺序。

两个 YouTube 场景共用一个包名，所以 17 个测试项对应 16 个独立包名；结果中的数量按测试项计。

例如：

```bash
./gradlew run --args="-t 1 -a 10"
./gradlew run --args="-t 4 -a 11 -f 2048 -m 5"
```

结果目录形如 `时间_workload10_onlyZram`、`时间_workload11_zswap2048_m5`。
`summary.txt` 记录 `config.workload`、`config.appCount` 和实际启动顺序 `config.appOrder`。为兼容比较工具保留 `config.appSet`，其值也改为数量，不再是旧编号。

下一次长测运行：

```bash
bash test2.sh
```

先用 17 项、无 Swap 预热一次，再遍历 10～17 项 × 1024/2048/4096 MB × 5%/10% zswap 池，共 48 组正式配置，每组默认 10 轮。普通配置失败后记录并继续；手动中断停止。终端日志自动保存为 `logs/test2_terminal_时间.log`。

此脚本沿用原 test2 的 zswap 范围，并不包含所有 Swap 模式。旧 test.sh/test3.sh 和其他辅助脚本的参数已迁移为数量；脚本文件名保留。
