#!/bin/zsh
set -euo pipefail

project_root="${0:A:h}"
cd "$project_root"

if [[ "$(uname -s)" != "Darwin" ]]; then
  print -u2 "Stardew Save Bridge is a macOS app."
  exit 1
fi

python_candidates=("${BRIDGE_PYTHON:-}" python3.14 python3.13 python3.12 python3.11 python3)
chosen_python=""
for candidate in "${python_candidates[@]}"; do
  if [[ -n "$candidate" ]] && command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>/dev/null; then
      chosen_python="$candidate"
      break
    fi
  fi
done

if [[ -z "$chosen_python" ]]; then
  print -u2 "Python 3.11 or newer is required. Install it, then run this installer again."
  print -u2 "Python downloads: https://www.python.org/downloads/macos/"
  exit 1
fi

print "Using $($chosen_python --version)"
if [[ ! -x .venv/bin/python ]]; then
  "$chosen_python" -m venv .venv
fi

print "Installing the app's Python requirements…"
.venv/bin/python -m pip install -e '.[build]'

print "Building the Mac app and launcher icon…"
./scripts/build_app.sh

app_path="${BRIDGE_ARTIFACT_DIR:-$HOME/Applications}/Stardew Save Bridge.app"
print "Installed: $app_path"
if ! command -v idevice_id >/dev/null 2>&1 || ! command -v ideviceinstaller >/dev/null 2>&1 || ! command -v afcclient >/dev/null 2>&1; then
  print "iPad USB tools are still needed before transfers can be enabled."
  print "See: $project_root/docs/ipad-usb-setup.md"
fi
if [[ "${BRIDGE_SKIP_OPEN:-0}" != "1" ]]; then
  open "$app_path"
fi
