# iPad USB setup

The app reads Stardew Valley's File Sharing Documents through [libimobiledevice's AFC/HouseArrest tools](https://github.com/libimobiledevice/libimobiledevice). It does not need macFUSE, ifuse, a mounted drive, or changes to Mac startup security.

1. Close Stardew Valley on both devices. Connect the iPad with a USB cable, unlock it, and tap **Trust This Computer** if prompted.
2. Install the tools with [Homebrew](https://brew.sh/):

   ```bash
   brew install libimobiledevice ideviceinstaller
   ```

3. Check pairing: `idevice_id --list` should show one device and `idevicepair validate` should succeed.
4. From the repository, run the read-only check:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/check_prerequisites.py
   ```

   It finds Stardew Valley by its File Sharing setting, downloads a temporary copy of visible farm folders to the Mac for inspection, and removes that copy after the check. It does not change the iPad.

5. Open the app and click **Refresh saves**. Confirm the exact farm name and money on each device before preparing a transfer.

If no farm appears, open the iPad's Files app or Finder File Sharing and check that Stardew Valley exposes Documents. The app cannot access a private game container or bypass the iPad sandbox.
