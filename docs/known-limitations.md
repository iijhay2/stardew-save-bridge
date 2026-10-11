# Known limitations

- The connected iPad was detected, trusted, and Stardew Valley was listed as installed. Direct File Sharing visibility and Documents mounting are **not yet verified** because compatible `ifuse` and macFUSE are unavailable on this Mac. No iPad write has been performed.
- Homebrew core `ifuse` currently depends on Linux-only `libfuse` on this macOS 27 machine. The app reports the missing dependency and disables transfer.
- Save metadata does not prove the installed Mac and iPad game versions are compatible. The app shows a warning for every transfer and asks for explicit acknowledgement. It does not claim to detect every downgrade path.
- The app recognizes `_old`, `_SVBAK`, and `_SVEMERG` files as supplemental files. It copies the whole selected farm folder and never treats an emergency save as a separately compatible desktop save.
- A new destination has no previous farm folder to archive. The app records this and verifies a source backup before creating the destination.
- macFUSE filesystem renames may not provide the same atomicity as local APFS. A disconnect or system failure during a write can still require manual restore from the verified archive.
- The app uses the standard Mac location `~/.config/StardewValley/Saves`. Custom save locations and mod conversion are not supported.
- Backups remain on the Mac until manually deleted from the Application Support backup folder. The app does not manage retention or cloud copies.
- The local `.app` build is ad hoc signed. Developer ID signing and Apple notarization are still needed for general distribution.
