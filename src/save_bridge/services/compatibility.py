from save_bridge.models import FarmSave


def compatibility_warning(source: FarmSave, destination: FarmSave | None) -> str:
    """Save metadata alone cannot prove the installed destination game is compatible."""
    if destination is None:
        return "The destination has no copy of this farm. Confirm its installed game is current."
    a = source.game_version
    b = destination.game_version
    if a and b and a != b:
        return (
            f"These saves report different game versions ({a} and {b}). "
            "Confirm the destination game is updated before continuing."
        )
    return (
        "Installed game-version compatibility cannot be confirmed from save files. "
        "Check both devices before continuing."
    )
