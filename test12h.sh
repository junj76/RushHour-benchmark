#!/usr/bin/env bash
set -euo pipefail
trap 'exit 130' INT
trap 'exit 143' TERM
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# 20 组参数 × 轻/中/重三种负载，共 60 组实验。
# 轻/中各 1 轮，重型 2 轮，共 1000 次应用操作；预计约 12 小时，非硬性截止。
# 基础负载约 5 小时 33 分 + 静置 5 小时，另加重启、初始化和页面超时。
# 每组由 Main 自动重启、初始化 Swap、静置 5 分钟；不是每轮都重启。
unset ANDROID_ADB_SERVER_HOST ANDROID_ADB_SERVER_PORT
run_id="$(date +%Y%m%d_%H%M%S)"
output_dir="logs/test12h_${run_id}"
mkdir -p "$output_dir"
summary="$output_dir/results.tsv"
printf 'config\texit_code\tcompleted\tfailed\texpected\tseconds\tlog\n' > "$summary"

configs=("0" "1")
for interval in 10 30 60; do
    for size in 1024 2048 4096; do
        configs+=("2 -f $size -w $interval")
    done
done
for size in 1024 2048 4096; do
    configs+=("3 -f $size")
done
for pool in 5 10; do
    for size in 1024 2048 4096; do
        configs+=("4 -f $size -m $pool")
    done
done

plans=()
expected_counts=()
app_counts=(6 10 17)
round_counts=(1 1 2)
for load in 0 1 2; do
    for config in "${configs[@]}"; do
        plans+=("-t $config -a ${app_counts[$load]} --rounds ${round_counts[$load]}")
        expected_counts+=("$((app_counts[$load] * round_counts[$load]))")
    done
done

batch_started=$SECONDS
has_failures=0
for index in "${!plans[@]}"; do
    number=$((index + 1))
    printf -v label 'check12h_%s_%02d' "$run_id" "$number"
    log="$output_dir/$(printf '%02d' "$number").log"
    args="${plans[$index]} -p $label"
    expected=${expected_counts[$index]}
    printf '\n[%d/%d] %s\n终端日志：%s\n' "$number" "${#plans[@]}" "$args" "$log"
    started=$SECONDS
    exit_code=0
    if ./gradlew --console=plain run --args="$args" 2>&1 | tee "$log"; then
        :
    else
        exit_code=$?
    fi
    if ((exit_code == 130 || exit_code == 143)); then
        printf '测试已中断，不再启动下一组。\n'
        exit "$exit_code"
    fi
    completed=$(grep -cE '\[app-actions\]\[[^]]+\] completed' "$log" || true)
    failed=$(grep -cE '\[app-actions\]\[[^]]+\] failed with exit code' "$log" || true)
    elapsed=$((SECONDS - started))
    printf '%s\t%d\t%d\t%d\t%d\t%d\t%s\n' \
        "$args" "$exit_code" "$completed" "$failed" "$expected" "$elapsed" "$log" >> "$summary"
    if ((exit_code != 0 || failed != 0 || completed != expected)); then
        has_failures=1
        printf '本组存在失败或缺失：退出码=%d，通过=%d，失败=%d，预期=%d；继续下一组。\n' \
            "$exit_code" "$completed" "$failed" "$expected"
    fi
    printf '本组耗时 %d 分 %d 秒；累计 %d 分钟。\n' \
        "$((elapsed / 60))" "$((elapsed % 60))" "$(((SECONDS - batch_started) / 60))"
done

printf '\n全部配置已尝试，结果汇总：%s\n' "$summary"
if ((has_failures)); then
    printf '有配置或操作未通过，请检查 results.tsv 和对应日志。\n'
    exit 1
fi
printf '轻、中、重负载的 60 组实验均完成预期操作。\n'
