#!/bin/zsh
set -euo pipefail

project_root="${0:A:h}"
cd "$project_root"
install_log="$HOME/Library/Logs/Stardew Save Bridge/install.log"
/bin/mkdir -p "${install_log:h}"
: > "$install_log"

if [[ "$(uname -s)" != "Darwin" ]]; then
  print -u2 "Stardew Save Bridge needs a Mac."
  exit 1
fi

brew_script=""
finish_install() {
  local result=$?
  if [[ -n "$brew_script" && -f "$brew_script" ]]; then
    /bin/rm "$brew_script"
  fi
  if (( result != 0 )); then
    print -u2 ""
    print -u2 "Setup stopped before the app was ready. Check the message above, then run this installer again."
    if [[ -s "$install_log" ]]; then
      print -u2 "If you need help, share the setup log: $install_log"
    fi
    if [[ -t 0 ]]; then
      read -r "?Press Return to close this window."
    fi
  fi
}
trap finish_install EXIT

export PATH="/opt/homebrew/bin:/usr/local/bin:/opt/local/bin:$PATH"
brew_bin=""
brew_prefix=""

ensure_homebrew() {
  if command -v brew >/dev/null 2>&1; then
    brew_bin="$(command -v brew)"
  else
    print "Setting up the Mac tools needed to connect your iPad…"
    print "macOS may ask for your administrator password during this one-time setup."
    brew_script="$(mktemp -t stardew-homebrew-install)"
    /usr/bin/curl -fsSL "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh" -o "$brew_script"
    /bin/bash "$brew_script"
    for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
      if [[ -x "$candidate" ]]; then
        brew_bin="$candidate"
        break
      fi
    done
    if [[ -z "$brew_bin" ]]; then
      print -u2 "The Mac tools could not be found after setup."
      return 1
    fi
  fi
  brew_prefix="$("$brew_bin" --prefix)"
  export PATH="$brew_prefix/bin:$brew_prefix/opt/python@3.13/bin:$PATH"
}

usb_tools_ready() {
  command -v idevice_id >/dev/null 2>&1 &&
    command -v ideviceinfo >/dev/null 2>&1 &&
    command -v ideviceinstaller >/dev/null 2>&1 &&
    command -v afcclient >/dev/null 2>&1
}

if ! usb_tools_ready; then
  ensure_homebrew
  print "Installing the iPad connection tools…"
  "$brew_bin" install libimobiledevice ideviceinstaller
  if ! usb_tools_ready; then
    print -u2 "The iPad connection tools did not finish installing."
    exit 1
  fi
fi

python_candidates=("${BRIDGE_PYTHON:-}" python3.14 python3.13 python3.12 python3.11 python3)
chosen_python=""
for candidate in "${python_candidates[@]}"; do
  if [[ -n "$candidate" ]] && command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] <= (3, 14)))' 2>/dev/null; then
      chosen_python="$candidate"
      break
    fi
  fi
done

if [[ -z "$chosen_python" ]]; then
  ensure_homebrew
  print "Installing Python for the app…"
  "$brew_bin" install python@3.13
  chosen_python="$brew_prefix/opt/python@3.13/bin/python3.13"
  if [[ ! -x "$chosen_python" ]]; then
    print -u2 "Python did not finish installing."
    exit 1
  fi
fi

print "Installing Stardew Save Bridge…"
if [[ -d .venv ]] && {
  [[ ! -x .venv/bin/python ]] ||
  ! .venv/bin/python -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] <= (3, 14)))' 2>/dev/null
}; then
  old_environment=".venv.previous.$(/bin/date +%Y%m%d%H%M%S)"
  print "Refreshing an older app setup…"
  /bin/mv .venv "$old_environment"
fi
if [[ ! -x .venv/bin/python ]]; then
  "$chosen_python" -m venv .venv
fi
.venv/bin/python -m pip install -e '.[build]' >> "$install_log" 2>&1

print "Creating the app and launcher icon…"
./scripts/build_app.sh >> "$install_log" 2>&1

app_path="${BRIDGE_ARTIFACT_DIR:-$HOME/Applications}/Stardew Save Bridge.app"
print "Ready! You can open Stardew Save Bridge from your home Applications folder."
if [[ "${BRIDGE_SKIP_OPEN:-0}" != "1" ]]; then
  open "$app_path"
fi
