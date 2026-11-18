#!/usr/bin/env bash
set -uo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# 重型负载：1 组重型预热 + 学长 test.sh 的 20 组正式参数。
# 沿用程序默认每组 10 轮；主程序每组自动重启、静置 5 分钟。
# 普通失败后记录并继续；Ctrl+C 时停止；应用脚本失败仍需查看终端日志。
trap 'exit 130' INT
trap 'exit 143' TERM
unset ANDROID_ADB_SERVER_HOST ANDROID_ADB_SERVER_PORT
mkdir -p logs
terminal_log="logs/test_heavy_terminal_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee "$terminal_log") 2>&1
printf '终端日志：%s\n' "$terminal_log"

# 与学长脚本一样继续下一组，同时把失败命令及退出码写入日志。
trap 'code=$?; printf "[测试失败] exit=%d command=%s\n" "$code" "$BASH_COMMAND"' ERR

# warmup
./gradlew --console=plain run --args="-t 0 -a 17 -p warmup"

# no flash
./gradlew --console=plain run --args="-t 0 -a 17"

# zram
./gradlew --console=plain run --args="-t 1 -a 17"

# zram+writeback
./gradlew --console=plain run --args="-t 2 -a 17 -f 1024 -w 10"
./gradlew --console=plain run --args="-t 2 -a 17 -f 2048 -w 10"
./gradlew --console=plain run --args="-t 2 -a 17 -f 4096 -w 10"

./gradlew --console=plain run --args="-t 2 -a 17 -f 1024 -w 30"
./gradlew --console=plain run --args="-t 2 -a 17 -f 2048 -w 30"
./gradlew --console=plain run --args="-t 2 -a 17 -f 4096 -w 30"

./gradlew --console=plain run --args="-t 2 -a 17 -f 1024 -w 60"
./gradlew --console=plain run --args="-t 2 -a 17 -f 2048 -w 60"
./gradlew --console=plain run --args="-t 2 -a 17 -f 4096 -w 60"

# flash swap
./gradlew --console=plain run --args="-t 3 -a 17 -f 1024"
./gradlew --console=plain run --args="-t 3 -a 17 -f 2048"
./gradlew --console=plain run --args="-t 3 -a 17 -f 4096"

# zswap
./gradlew --console=plain run --args="-t 4 -a 17 -f 1024 -m 5"
./gradlew --console=plain run --args="-t 4 -a 17 -f 2048 -m 5"
./gradlew --console=plain run --args="-t 4 -a 17 -f 4096 -m 5"

./gradlew --console=plain run --args="-t 4 -a 17 -f 1024 -m 10"
./gradlew --console=plain run --args="-t 4 -a 17 -f 2048 -m 10"
./gradlew --console=plain run --args="-t 4 -a 17 -f 4096 -m 10"
