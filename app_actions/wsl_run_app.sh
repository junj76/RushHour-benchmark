#!/usr/bin/env bash
# Run Windows UI automation from a WSL2 scheduler.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_exe="${APP_ACTION_PYTHON:-/mnt/d/codeing/python.exe}"
if [[ ! -f "$python_exe" ]]; then
    printf '%s\n' "Set APP_ACTION_PYTHON to the WSL path of Windows Python with uiautomator2." >&2
    exit 1
fi
windows_script="$(wslpath -w "$script_dir/ENapp/run_app.py")"
# 将 Windows ADB 路径和输出编码传给 Windows Python。
export ADBUTILS_ADB_PATH="$(wslpath -w "$(command -v adb.exe)")"
export PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
export WSLENV="${WSLENV:+$WSLENV:}ADBUTILS_ADB_PATH:PYTHONUNBUFFERED:PYTHONIOENCODING"
exec "$python_exe" "$windows_script" "$@"
