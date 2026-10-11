# Stardew Save Bridge

A small macOS app for choosing **one Stardew Valley farm** and copying its complete save folder between a Mac and a USB-connected iPad. It shows the farm name, player, money on each device, and save date so you can pick the right farm when you have several.

![Farm Journal showing two example farms and their Mac/iPad money](docs/farm-journal-preview.png)

> **Hardware status:** Direct USB reading has been verified with two real iPad farms on macOS 27. Upload, readback, replacement, and cleanup passed with a disposable test folder in Stardew's shared Documents area. The full in-game transfer checklist still needs a disposable farm before relying on this with a real save; see [hardware acceptance](docs/hardware-acceptance.md).

## What it does

- Lists multiple farms and lets you search by farm or farmer.
- Compares the Mac and iPad copies of the selected farm, including each copy's money.
- Lets **you** choose Mac or iPad as the source. It never silently chooses the newest save.
- Makes and verifies a backup of the source and any existing destination before showing the final confirmation.
- Copies the whole farm folder, checks the result, records local history, and offers restore from a verified backup.

The app is local only. There is no account, cloud sync, telemetry, or background transfer.

## Requirements

| Requirement | Why it is needed |
| --- | --- |
| macOS | This is a native Mac app. The current build has been checked on macOS 27 with Apple silicon; other versions need testing. |
| [Python 3.11 or newer](https://www.python.org/downloads/macos/) | Builds the iconed app on each workstation. Python 3.14 is the version used for the current build. |
| Stardew Valley on the Mac and iPad | The Mac copy is read from `~/.config/StardewValley/Saves`. The iPad edition must expose its Documents folder through normal File Sharing. |
| USB cable and a trusted, unlocked iPad | USB access is deliberate; the app does not use network pairing. |
| [libimobiledevice](https://github.com/libimobiledevice/libimobiledevice) and [ideviceinstaller](https://github.com/libimobiledevice/ideviceinstaller) | Detect the iPad, find Stardew Valley's File Sharing app, and read/write its Documents folder over USB. No filesystem driver or kernel setting change is needed. |

The app opens and shows Mac farms without iPad tools. Transfer buttons stay disabled until the iPad can be scanned.

## Install on a Mac

1. Clone the repository and enter it:

   ```bash
   git clone https://github.com/iijhay2/stardew-save-bridge.git
   cd stardew-save-bridge
   ```

2. Install [Python 3.11+](https://www.python.org/downloads/macos/) if needed. Then double-click **Install Stardew Save Bridge.command** in Finder, or run:

   ```bash
   "./Install Stardew Save Bridge.command"
   ```

   The installer creates a local `.venv`, installs the Python build requirements, builds and locally signs **Stardew Save Bridge.app**, places the iconed launcher in `~/Applications`, and opens it. You can later launch it from Finder or with:

   ```bash
   open "$HOME/Applications/Stardew Save Bridge.app"
   ```

3. For iPad transfers, install [Homebrew](https://brew.sh/) if needed, then install the USB tools:

   ```bash
   brew install libimobiledevice ideviceinstaller
   ```

   The [libimobiledevice formula](https://formulae.brew.sh/formula/libimobiledevice) includes `afcclient`; [ideviceinstaller](https://formulae.brew.sh/formula/ideviceinstaller) provides app discovery. The app also looks for tools in Homebrew and MacPorts locations when launched from Finder. See the [USB setup guide](docs/ipad-usb-setup.md) for connection checks.

4. Connect and unlock the iPad, tap **Trust This Computer** if prompted, close Stardew Valley on both devices, and run the read-only check:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/check_prerequisites.py
   ```

   The check should name Stardew Valley in File Sharing and list visible farm folders. It only reads them and deletes its temporary Mac snapshot afterward. If it cannot connect, you can still inspect Mac farms and restore existing Mac backups; see [known limitations](docs/known-limitations.md).

## Transfer a farm

1. Close Stardew Valley on both devices. Connect and unlock the iPad.
2. Open the app and select the **exact farm** in the left list. Check its name and the Mac/iPad money amounts.
3. Compare the two cards and select **Use this copy as source** on Mac or iPad. A missing copy is shown as a new destination.
4. Click **Prepare Mac → iPad** or **Prepare iPad → Mac**. The app rescans both copies, creates verified backups, and prepares the transfer.
5. Read the final review: source, destination, exact target folder, file count, and backup paths. Confirm only if that is the change you want.
6. After success, eject the iPad safely. Open Stardew Valley and check that the farm loads with the expected money and progress.

If a save changes between scanning and writing, the app stops and asks you to refresh. The game-version warning is a reminder to check that both installed games are compatible; save metadata alone cannot prove this.

## Restore a backup

Open **Backups & history**, select a verified archive, choose Mac or iPad as the target, and click **Review restore**. The app backs up any current target farm and asks for another final confirmation. A Mac restore works even when the iPad is disconnected.

Backups and history stay in `~/Library/Application Support/Stardew Save Bridge/`. They are not deleted automatically. If a transfer is interrupted, consult [hardware acceptance and recovery checks](docs/hardware-acceptance.md) before trying again.

## Update or rebuild

In the cloned repository, run `git pull --ff-only` and rerun **Install Stardew Save Bridge.command**. The installer rebuilds the launcher; your backups remain outside the repository. For a source run or developer checks, see the commands below.

```bash
.venv/bin/python -m pip install -e '.[dev]'
PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/mypy src
```

If Qt cannot find its platform plugin when running from the hidden `.venv` on macOS, copy `.venv/lib/python*/site-packages/PySide6/Qt/plugins/platforms/` to a normal temporary directory and set `QT_QPA_PLATFORM_PLUGIN_PATH` to that directory. The built app carries its Qt plugins.

The local app uses an ad hoc signature. General distribution through macOS Gatekeeper would require Developer ID signing and notarization; the current workflow builds on each user's Mac with [PyInstaller](https://pyinstaller.org/en/stable/).

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| No farms on the Mac | Save a farm in Stardew Valley and confirm the standard `~/.config/StardewValley/Saves` folder exists. Custom save locations are not supported yet. |
| iPad needs setup | Connect by USB, unlock and trust it, install the USB tools, then click **Refresh saves**. Run the read-only prerequisite script for the exact error. |
| Stardew is installed but no iPad farm appears | The iPad edition may not expose its Documents folder through File Sharing. The app cannot bypass the iPad sandbox. |
| Transfer stops after review | A save may have changed, Stardew may still be running on the Mac, storage may be low, or the iPad may have disconnected. Refresh and inspect the message; verified backups remain available. |
| App does not build | Check `python3 --version` and rerun the installer with an internet connection. On a Mac with several Python versions, set `BRIDGE_PYTHON` to the wanted Python executable. |

## Safety and scope

The app uses [libimobiledevice's `afcclient` HouseArrest support](https://github.com/libimobiledevice/libimobiledevice) to access Stardew Valley's File Sharing Documents folder directly over USB. It does not mount a volume, change kernel settings, use `--root` or `--container`, jailbreak access, edit save contents, resolve conflicts automatically, or sync in the background. It identifies `_old`, `_SVBAK`, and `_SVEMERG` files but transfers only a selected standard whole farm folder. A disconnect during an iPad write may still require manual recovery; see [known limitations](docs/known-limitations.md).

## Design and credits

- The four-color theme comes from this [Color Hunt palette](https://colorhunt.co/palette/f6e2e9fefaf3b8cfb384a282): `#F6E2E9`, `#FEFAF3`, `#B8CFB3`, and `#84A282`. Darker shades are used where text or action states need more contrast.
- The square borders and offset shadows are inspired by [RetroUI](https://retroui.io/). RetroUI is a React/Tailwind library; this native app recreates the visual direction in Qt and does not bundle its components.
- The interface uses [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/). The installable Mac app is made with [PyInstaller](https://pyinstaller.org/en/stable/).
- iPad access relies on the open [libimobiledevice](https://github.com/libimobiledevice/libimobiledevice) and [ideviceinstaller](https://github.com/libimobiledevice/ideviceinstaller) projects. Their installation and licenses are separate from this repository.
- The pixel flower artwork and app icon in this repository were drawn for this project. The screenshot uses disposable example farms. This is an unofficial Stardew Valley utility and is not affiliated with the game creators.
