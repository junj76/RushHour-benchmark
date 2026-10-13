#!/usr/bin/env bash
# Run Windows UI automation from a WSL2 scheduler.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_exe="${APP_ACTION_PYTHON:-$script_dir/.venv/bin/python3}"
if [[ ! -x "$python_exe" ]]; then
    printf '%s\n' "Create app_actions/.venv and install requirements first." >&2
    exit 1
fi
export ADBUTILS_ADB_PATH="${ADBUTILS_ADB_PATH:-adb.exe}"
exec "$python_exe" "$script_dir/run_app.py" "$@"
