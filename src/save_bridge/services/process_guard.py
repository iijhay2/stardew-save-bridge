import subprocess

from save_bridge.errors import BridgeError


def ensure_game_closed() -> None:
    try:
        result = subprocess.run(
            ["/usr/bin/pgrep", "-fl", "Stardew Valley|StardewValley"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BridgeError("Could not check whether Stardew Valley is running on this Mac") from exc
    if result.returncode == 0 and result.stdout.strip():
        raise BridgeError("Close Stardew Valley on your Mac before transferring a save")
    if result.returncode not in (0, 1):
        raise BridgeError("Could not confirm Stardew Valley is closed on this Mac")
