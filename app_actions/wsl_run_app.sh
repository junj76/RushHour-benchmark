#!/usr/bin/env bash
# Always use the project venv, independent of shell activation or Gradle's PATH.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_exe="$script_dir/.venv/bin/python"
if [[ ! -x "$python_exe" ]]; then
    printf 'App action Python is unavailable: %s\n' "$python_exe" >&2
    printf '%s\n' "Create app_actions/.venv and install adbutils uiautomator2." >&2
    exit 1
fi
export PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
exec "$python_exe" "$script_dir/ENapp/run_app.py" "$@"
