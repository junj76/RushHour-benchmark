#!/usr/bin/env bash
# Allow Windows Python to share the Windows ADB server when running under WSL.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_exe="${APP_ACTIONS_PYTHON:-$script_dir/.venv/bin/python}"
if [[ -z "${APP_ACTIONS_PYTHON:-}" ]] && command -v adb.exe >/dev/null && command -v python.exe >/dev/null; then
    python_exe="$(command -v python.exe)"
fi
if [[ ! -x "$python_exe" ]]; then
    printf 'App action Python is unavailable: %s\n' "$python_exe" >&2
    printf '%s\n' "Create app_actions/.venv and install adbutils uiautomator2." >&2
    exit 1
fi
export PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
printf '[app-actions] Python: %s\n' "$python_exe" >&2
if [[ "${1:-}" == --check-device ]]; then
    exec "$python_exe" -c 'import sys, adbutils, uiautomator2; devices = adbutils.adb.device_list(); print("[app-actions] Python:", sys.executable, "devices:", devices, flush=True); sys.exit(0 if len(devices) == 1 else "Expected exactly one authorized Android device")'
fi
runner="$script_dir/ENapp/run_app.py"
if [[ "$python_exe" == *.exe ]]; then
    runner="$(wslpath -w "$runner")"
fi
exec "$python_exe" "$runner" "$@"
