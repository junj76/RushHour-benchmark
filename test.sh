#!/usr/bin/env bash
set -uo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
trap 'exit 130' INT
trap 'exit 143' TERM
unset ANDROID_ADB_SERVER_HOST ANDROID_ADB_SERVER_PORT
mkdir -p logs
terminal_log="logs/test_terminal_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee "$terminal_log") 2>&1
printf '终端日志：%s\n' "$terminal_log"

# 按学长原版的 20 组参数，分别测试四种数量；每组默认 10 轮。
workloads=(12 14 16)
sizes=(1024 4096)
intervals=(10 60)
pools=(5 10)

# 普通失败后记录并继续，手动中断则停止，不再启动下一组。
run_config() {
    printf '\n运行配置：%s\n' "$*"
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

# 预热使用全部 17 项，对应原版的重型预热，仅执行一次。
run_config -t 0 -a 17 -p warmup

for count in "${workloads[@]}"; do
    # no flash / zram
    run_config -t 0 -a "$count"
    run_config -t 1 -a "$count"

    # zram + writeback：3 种间隔 × 3 种容量
    for interval in "${intervals[@]}"; do
        for size in "${sizes[@]}"; do
            run_config -t 2 -a "$count" -f "$size" -w "$interval"
        done
    done

    # flash swap：3 种容量
    for size in "${sizes[@]}"; do
        run_config -t 3 -a "$count" -f "$size"
    done

    # zswap：2 种池比例 × 3 种容量；仅此模式传 -m。
    for pool in "${pools[@]}"; do
        for size in "${sizes[@]}"; do
            run_config -t 4 -a "$count" -f "$size" -m "$pool"
        done
    done

    for pool in "${pools[@]}"; do
        for size in "${sizes[@]}"; do
            run_config -t 5 -a "$count" -f "$size" -m "$pool"
        done
    done
done
