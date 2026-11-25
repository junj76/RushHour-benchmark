#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# 每项 14 个应用条目、默认 5 轮，使用固定操作脚本（-c 1）；共 23 次测试。
# 测试按执行顺序编号 1–23。容量按 1 GiB = 1024 MiB 换算。
# 每项测试的重启和静置由 Main.kt 负责；zRAM 写回间隔为 60 秒。
# 手机 MemTotal = 7737752 KiB；zRAM -z = round(7737752 / 1024 * zswap百分比 / 100)。
# zswap -m 2/5/7/9/27 对齐 zRAM -z 151/378/529/680/2040 MiB。
# -m 只能用整数百分比，-z 取最近整数 MiB；池上限近似相等，非字节级相等。
# 更换手机或内存配置后需重新换算这些固定值。

# 一、No Swap、Flash Swap、Only Zram
./gradlew run --args="-t 0 -a 14 -c 1 -p 1"
./gradlew run --args="-t 3 -a 14 -c 1 -f 1024 -p 2"
./gradlew run --args="-t 3 -a 14 -c 1 -f 2048 -p 3"
./gradlew run --args="-t 3 -a 14 -c 1 -f 3072 -p 4"
./gradlew run --args="-t 3 -a 14 -c 1 -f 4096 -p 5"
./gradlew run --args="-t 1 -a 14 -c 1 -d 1024 -z 0 -p 6"
./gradlew run --args="-t 1 -a 14 -c 1 -d 2048 -z 0 -p 7"
./gradlew run --args="-t 1 -a 14 -c 1 -d 3072 -z 0 -p 8"
./gradlew run --args="-t 1 -a 14 -c 1 -d 4096 -z 0 -p 9"

# 二、zswap：以 flash / 6 为目标，取最近整数 RAM 百分比
./gradlew run --args="-t 4 -a 14 -c 1 -f 1024 -m 2 -p 10"
./gradlew run --args="-t 4 -a 14 -c 1 -f 2048 -m 5 -p 11"
./gradlew run --args="-t 4 -a 14 -c 1 -f 3072 -m 7 -p 12"
./gradlew run --args="-t 4 -a 14 -c 1 -f 4096 -m 9 -p 13"

# 三、zRAM + WB：逻辑容量等于 flash，池上限对齐第二组 zswap
./gradlew run --args="-t 2 -a 14 -c 1 -d 1024 -z 151 -f 1024 -w 60 -p 14"
./gradlew run --args="-t 2 -a 14 -c 1 -d 2048 -z 378 -f 2048 -w 60 -p 15"
./gradlew run --args="-t 2 -a 14 -c 1 -d 3072 -z 529 -f 3072 -w 60 -p 16"
./gradlew run --args="-t 2 -a 14 -c 1 -d 4096 -z 680 -f 4096 -w 60 -p 17"

# 四、zRAM + WB：逻辑容量为 flash 的 1.5 倍，池容量保持不变
./gradlew run --args="-t 2 -a 14 -c 1 -d 1536 -z 151 -f 1024 -w 60 -p 18"
./gradlew run --args="-t 2 -a 14 -c 1 -d 3072 -z 378 -f 2048 -w 60 -p 19"
./gradlew run --args="-t 2 -a 14 -c 1 -d 4608 -z 529 -f 3072 -w 60 -p 20"
./gradlew run --args="-t 2 -a 14 -c 1 -d 6144 -z 680 -f 4096 -w 60 -p 21"

# 最后两项：flash 为 2 GiB，池上限对齐为约 2040 MiB（接近 2 GiB）
./gradlew run --args="-t 2 -a 14 -c 1 -d 8192 -z 2040 -f 2048 -w 60 -p 22"
./gradlew run --args="-t 4 -a 14 -c 1 -f 2048 -m 27 -p 23"
