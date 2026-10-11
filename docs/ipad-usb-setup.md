# iPad USB setup

1. Close Stardew Valley on both devices. Connect the iPad with a USB cable, unlock it, and trust this Mac.
2. Confirm the USB device is visible with `idevice_id --list` and pairing succeeds with `idevicepair validate`.
3. Install a macOS 27 compatible [macFUSE release](https://macfuse.github.io/2026/09/07/macfuse-5.4.0.html) and approve its required system extension in macOS settings if prompted.
4. After macFUSE is installed, try `brew install gromgit/fuse/ifuse-mac`. This [macOS-specific formula](https://github.com/gromgit/homebrew-fuse/blob/main/Formula/ifuse-mac.rb) requires macFUSE. It has not yet been tested on this macOS 27 machine. The Homebrew core `ifuse` formula depends on Linux `libfuse`, so `brew install ifuse` did not work here.
5. Run `PYTHONPATH=src .venv/bin/python scripts/check_prerequisites.py`. It uses the documented `ifuse --list-apps` and `ifuse --documents <detected-app-id>` path, lists farm folders, and unmounts without writing.

`ifuse` documents [File Sharing app discovery and Documents mounting](https://github.com/libimobiledevice/ifuse). If Stardew does not appear in its File Sharing list on the actual iPad, direct USB sync is unavailable. The app should remain in read-only Mac mode until a separately designed manual Finder import/export path is available.

Do not use `--container`, `--root`, jailbreak access, or an arbitrary app identifier.
