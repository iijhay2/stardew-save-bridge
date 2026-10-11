# Known limitations

- Direct USB reading of two actual iPad farm folders and a disposable folder upload, readback, replacement, and cleanup have passed on macOS 27. A complete Mac ↔ iPad transfer has not yet been checked by opening a disposable farm in both game editions.
- Save metadata does not prove the installed Mac and iPad game versions are compatible. The app warns on each transfer and asks for explicit acknowledgement.
- The app recognizes `_old`, `_SVBAK`, and `_SVEMERG` as supplemental files. It copies the selected whole farm folder and never treats an emergency save as a separately compatible desktop save.
- A new destination has no previous farm folder to archive. The app records this and verifies a source backup before creating the destination.
- An iPad disconnect or power loss during a write can interrupt the remote rename or rollback. The app preserves verified Mac backup archives so the farm can be restored manually.
- The app uses the standard Mac location `~/.config/StardewValley/Saves`. Custom save locations and mod conversion are not supported.
- Backups remain on the Mac until manually deleted from the Application Support backup folder. The app does not manage retention or cloud copies.
- The local `.app` build is ad hoc signed. Developer ID signing and Apple notarization are still needed for general distribution.
