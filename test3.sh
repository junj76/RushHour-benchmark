#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# 短测：每个模式 17 个测试项（含 YouTube Shorts 和 wikiHow），只跑 1 轮。
# 每个模式约 6 分钟负载 + 5 分钟静置 + 重启，合计预计 25–30 分钟。
# 仅用于验证配置及统计输出；内存压力不足时读写次数可能为 0。

# Flash Swap，映射容量 1024 MB
./gradlew run --args="-t 3 -a 17 -f 1024 --rounds 1 -p quick_flash"

# zRAM + writeback，后端 4096 MB，每 10 秒触发一次下刷
./gradlew run --args="-t 2 -a 17 -f 4096 -w 10 --rounds 1 -p quick_writeback"
