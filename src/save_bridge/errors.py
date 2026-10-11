class BridgeError(Exception):
    """A user-facing operation failure with a useful explanation."""


class ChangedSaveError(BridgeError):
    """A save changed after review, so the operation must be prepared again."""


class DeviceUnavailableError(BridgeError):
    """The connected iPad cannot be safely accessed."""


class OperationCancelled(BridgeError):
    """The user cancelled before a destination write."""
