#!/usr/bin/env bash
set -uo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
trap 'exit 130' INT
trap 'exit 143' TERM
unset ANDROID_ADB_SERVER_HOST ANDROID_ADB_SERVER_PORT
mkdir -p logs
terminal_log="logs/test2_terminal_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee "$terminal_log") 2>&1
printf '终端日志：%s\n' "$terminal_log"

# 沿用学长的预热和 zswap 参数；每组默认 10 轮，普通失败后继续。
# 8 种数量 × 3 种容量 × 2 种池比例 = 48 组正式配置。
workloads=({10..17})
sizes=(1024 2048 4096)
pools=(5 10)

run_config() {
    ./gradlew --console=plain run --args="$*"
    code=$?
    if ((code == 130 || code == 143)); then
        exit "$code"
    fi
    if ((code != 0)); then
        printf '[测试失败] exit=%d args=%s；继续下一组。\n' "$code" "$*"
    fi
    return 0
}

# 最大负载预热一次，对应原脚本的重型预热。
run_config -t 0 -a 17 -p warmup

for count in "${workloads[@]}"; do
    for pool in "${pools[@]}"; do
        for size in "${sizes[@]}"; do
            printf '\nworkload%d：zswap，容量=%d MB，池比例=%d%%\n' "$count" "$size" "$pool"
            run_config -t 4 -a "$count" -f "$size" -m "$pool"
        done
    done
done
