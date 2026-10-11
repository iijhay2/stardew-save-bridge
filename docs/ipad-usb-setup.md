# Connect your iPad

The installer includes the tools needed to read Stardew Valley's shared files over USB. No Mac security setting, filesystem driver, macFUSE, or ifuse is needed.

1. Close Stardew Valley on the Mac and iPad.
2. Connect the iPad with a USB data cable and unlock it.
3. Tap **Trust This Computer** on the iPad if asked.
4. Open **Stardew Save Bridge** and click **Refresh saves**. Select a farm and compare its name and money on both devices.

If the iPad still does not appear, unplug it and reconnect it, then run **Install Stardew Save Bridge.command** again. The installer checks and installs the USB tools. If Stardew Valley is missing from the app, open the game once on the iPad, create or save a farm, close it, and refresh.

The app reads Stardew Valley's Documents folder through Apple's File Sharing connection using [libimobiledevice](https://github.com/libimobiledevice/libimobiledevice). It cannot read files that iPadOS keeps private. Advanced users can run the read-only connection check from the repository:

```bash
PYTHONPATH=src .venv/bin/python scripts/check_prerequisites.py
```

The check only reads visible farm folders and removes its temporary Mac copy afterward.
