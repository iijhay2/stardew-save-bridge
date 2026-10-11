#!/bin/zsh
set -euo pipefail

project_root="${0:A:h:h}"
cd "$project_root"
artifact_root="${BRIDGE_ARTIFACT_DIR:-$HOME/Applications}"
mkdir -p "$artifact_root"

if [[ ! -x .venv/bin/python ]]; then
  print -u2 "Create the environment first: python3 -m venv .venv && .venv/bin/pip install -e '.[build]'"
  exit 1
fi

.venv/bin/python scripts/make_icon.py build/farm-journal.icns
.venv/bin/python -m PyInstaller \
  --noconfirm --clean --log-level WARN --windowed --onedir \
  --name "Stardew Save Bridge" \
  --distpath "$artifact_root" \
  --osx-bundle-identifier "local.stardewsavebridge.app" \
  --icon build/farm-journal.icns \
  --paths src \
  --add-data "src/save_bridge/resources:save_bridge/resources" \
  src/save_bridge/main.py

app_path="$artifact_root/Stardew Save Bridge.app"
xattr -cr "$app_path"
codesign --force --deep --sign - "$app_path"
codesign --verify --deep --strict "$app_path"
print "Built: $app_path"
print "This local build has an ad hoc signature; Developer ID distribution signing is still required."
