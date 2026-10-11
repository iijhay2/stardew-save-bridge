import os
import shutil
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from save_bridge.app_paths import AppPaths
from save_bridge.errors import BridgeError, ChangedSaveError, OperationCancelled
from save_bridge.models import Device, FarmSave, SaveManifest, ScanResult
from save_bridge.services.backup import BackupInfo, BackupService
from save_bridge.services.compatibility import compatibility_warning
from save_bridge.services.history import HistoryService
from save_bridge.services.ipad import USBBridge
from save_bridge.services.process_guard import ensure_game_closed
from save_bridge.services.save_scan import manifest_for, scan_root

Progress = Callable[[str], None]


@dataclass(frozen=True)
class PreparedTransfer:
    operation_id: str
    source: FarmSave
    destination: FarmSave | None
    source_backup: BackupInfo
    destination_backup: BackupInfo | None
    staged_source: Path
    warning: str | None
    source_location: str
    target_location: str

    @property
    def target_device(self) -> Device:
        return "ipad" if self.source.device == "mac" else "mac"


@dataclass(frozen=True)
class PreparedRestore:
    operation_id: str
    archive: BackupInfo
    target_device: Device
    destination: FarmSave | None
    destination_backup: BackupInfo | None
    staged_source: Path
    target_location: str


def _find(saves: tuple[FarmSave, ...], folder_id: str) -> FarmSave | None:
    return next((save for save in saves if save.folder_id == folder_id), None)


def _same_snapshot(expected: FarmSave | None, actual: FarmSave | None) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    return bool(expected.manifest and actual.manifest and expected.manifest == actual.manifest)


def replace_verified(
    target: Path, staged_source: Path, expected: SaveManifest, operation_id: str
) -> None:
    """Stage on the target filesystem and retain its old folder until verification."""
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    incoming = parent / f".bridge-incoming-{operation_id}"
    previous = parent / f".bridge-previous-{operation_id}"
    if incoming.exists() or previous.exists():
        raise BridgeError("A prior transfer stage needs inspection before retrying")
    moved_old = False
    try:
        shutil.copytree(staged_source, incoming)
        if manifest_for(incoming) != expected:
            raise BridgeError("The staged destination differs from the source")
        if target.exists():
            os.replace(target, previous)
            moved_old = True
        os.replace(incoming, target)
        if manifest_for(target) != expected:
            raise BridgeError("Destination verification failed after the write")
        if moved_old:
            shutil.rmtree(previous)
    except Exception as exc:
        recovery_error = None
        if moved_old and previous.exists():
            try:
                if target.exists():
                    shutil.rmtree(target)
                os.replace(previous, target)
            except OSError as restore_exc:
                recovery_error = restore_exc
        elif not moved_old and target.exists() and incoming.exists() is False:
            # A new destination may have been renamed into place before verification failed.
            try:
                shutil.rmtree(target)
            except OSError:
                pass
        if recovery_error:
            raise BridgeError(
                f"Transfer failed and automatic restoration was interrupted: {recovery_error}. "
                "Use the verified backup in History."
            ) from exc
        raise BridgeError(f"Transfer failed: {exc}") from exc
    finally:
        if incoming.exists():
            shutil.rmtree(incoming, ignore_errors=True)


class BridgeService:
    def __init__(
        self,
        paths: AppPaths | None = None,
        mac_root: Path | None = None,
        usb: USBBridge | None = None,
    ) -> None:
        self.paths = paths or AppPaths.default()
        self.paths.ensure()
        self.mac_root = mac_root or Path.home() / ".config" / "StardewValley" / "Saves"
        self.usb = usb or USBBridge(self.paths.staging)
        self.backups = BackupService(self.paths.backups)
        self.history = HistoryService(self.paths.history)

    @contextmanager
    def _roots(self) -> Iterator[tuple[Path, Path, str]]:
        with self.usb.mounted_documents() as (ipad_root, device_name, _app_id):
            yield self.mac_root, ipad_root, device_name

    @contextmanager
    def _restore_root(self, device: Device) -> Iterator[Path]:
        if device == "mac":
            yield self.mac_root
        else:
            with self.usb.mounted_documents() as (ipad_root, _device_name, _app_id):
                yield ipad_root

    def scan(self) -> ScanResult:
        mac = scan_root(self.mac_root, "mac")
        try:
            with self._roots() as (_mac_root, ipad_root, device_name):
                ipad = scan_root(ipad_root, "ipad")
            return ScanResult(mac, ipad, "Connected and ready", device_name)
        except (BridgeError, OSError, ValueError) as exc:
            return ScanResult(mac, (), str(exc))

    def prepare(
        self,
        selected_source: FarmSave,
        expected_destination: FarmSave | None,
        progress: Progress = lambda _step: None,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> PreparedTransfer:
        operation_id = uuid.uuid4().hex[:16]
        folder_id = selected_source.folder_id
        stage_root = self.paths.staging / operation_id
        self.history.append(operation_id, "starting", farm=folder_id, source=selected_source.device)
        try:
            progress("Checking both farm copies")
            if cancelled():
                raise OperationCancelled("Preparation cancelled")
            ensure_game_closed()
            with self._roots() as (mac_root, ipad_root, _device_name):
                mac = scan_root(mac_root, "mac")
                ipad = scan_root(ipad_root, "ipad")
                source = _find(mac if selected_source.device == "mac" else ipad, folder_id)
                destination = _find(ipad if selected_source.device == "mac" else mac, folder_id)
                target_root = ipad_root if selected_source.device == "mac" else mac_root
                target_path = target_root / folder_id
                if destination is None and (target_path.exists() or target_path.is_symlink()):
                    raise BridgeError(
                        "The destination path exists but is not a standard farm folder. "
                        "Inspect it before transferring."
                    )
                if not _same_snapshot(selected_source, source) or not _same_snapshot(
                    expected_destination, destination
                ):
                    raise ChangedSaveError(
                        "A farm changed since the last scan. Refresh and review again."
                    )
                if (
                    source is None
                    or not source.valid
                    or (destination is not None and not destination.valid)
                ):
                    raise BridgeError(
                        "One of the selected farms is incomplete or could not be verified"
                    )
                warning = compatibility_warning(source, destination)
                stage_root.mkdir(parents=True, exist_ok=False)
                progress(f"Backing up {source.device.title()} farm")
                source_backup = self.backups.create(source, operation_id, cancelled)
                target_backup = None
                if destination is not None:
                    progress(f"Backing up {destination.device.title()} farm")
                    target_backup = self.backups.create(destination, operation_id, cancelled)
                progress("Preparing and verifying transfer copy")
                if cancelled():
                    raise OperationCancelled("Preparation cancelled")
                staged_source = stage_root / folder_id
                shutil.copytree(source.path, staged_source)
                if manifest_for(staged_source) != source.manifest:
                    raise BridgeError("The prepared copy differs from the selected farm")
            source_location = (
                str(self.mac_root / folder_id)
                if source.device == "mac"
                else f"iPad File Sharing/Stardew Documents/{folder_id}"
            )
            target_location = (
                str(self.mac_root / folder_id)
                if source.device == "ipad"
                else f"iPad File Sharing/Stardew Documents/{folder_id}"
            )
            prepared = PreparedTransfer(
                operation_id,
                source,
                destination,
                source_backup,
                target_backup,
                staged_source,
                warning,
                source_location,
                target_location,
            )
            self.history.append(
                operation_id,
                "prepared",
                farm=folder_id,
                source=source.device,
                target=prepared.target_device,
                source_backup=str(source_backup.path),
                destination_backup=str(target_backup.path) if target_backup else None,
                target_was_empty=destination is None,
            )
            return prepared
        except Exception as exc:
            shutil.rmtree(stage_root, ignore_errors=True)
            self.history.append(
                operation_id,
                "cancelled" if isinstance(exc, OperationCancelled) else "failed",
                farm=folder_id,
                error=str(exc),
            )
            if isinstance(exc, (BridgeError, OSError, ValueError)):
                raise
            raise BridgeError(f"Could not prepare transfer: {exc}") from exc

    def cancel(self, prepared: PreparedTransfer) -> None:
        self.history.append(prepared.operation_id, "cancelled", farm=prepared.source.folder_id)
        shutil.rmtree(prepared.staged_source.parent, ignore_errors=True)

    def execute(self, prepared: PreparedTransfer, progress: Progress = lambda _step: None) -> None:
        operation_id = prepared.operation_id
        verified = False
        try:
            ensure_game_closed()
            self.backups.verify(prepared.source_backup.path)
            if prepared.destination_backup:
                self.backups.verify(prepared.destination_backup.path)
            if manifest_for(prepared.staged_source) != prepared.source.manifest:
                raise BridgeError("Prepared save changed before writing")
            progress("Rechecking connected farms")
            with self._roots() as (mac_root, ipad_root, _device_name):
                mac = scan_root(mac_root, "mac")
                ipad = scan_root(ipad_root, "ipad")
                source = _find(
                    mac if prepared.source.device == "mac" else ipad, prepared.source.folder_id
                )
                destination = _find(
                    ipad if prepared.source.device == "mac" else mac, prepared.source.folder_id
                )
                if not _same_snapshot(prepared.source, source) or not _same_snapshot(
                    prepared.destination, destination
                ):
                    raise ChangedSaveError(
                        "A farm changed after backup. No write was made; refresh and review again."
                    )
                target_root = ipad_root if prepared.target_device == "ipad" else mac_root
                target = target_root / prepared.source.folder_id
                if prepared.destination is None and (target.exists() or target.is_symlink()):
                    raise ChangedSaveError(
                        "A destination path appeared after backup. No write was made."
                    )
                self.history.append(
                    operation_id,
                    "writing",
                    farm=prepared.source.folder_id,
                    target=prepared.target_device,
                )
                progress(f"Copying farm to {prepared.target_device.title()}")
                assert prepared.source.manifest is not None
                if prepared.target_device == "ipad":
                    self.usb.replace_verified(
                        prepared.source.folder_id,
                        prepared.staged_source,
                        prepared.source.manifest,
                        operation_id,
                        destination.manifest if destination else None,
                    )
                else:
                    replace_verified(
                        target, prepared.staged_source, prepared.source.manifest, operation_id
                    )
                verified = True
            progress("Transfer verified")
            self.history.append(
                operation_id,
                "succeeded",
                farm=prepared.source.folder_id,
                source=prepared.source.device,
                target=prepared.target_device,
                source_backup=str(prepared.source_backup.path),
                destination_backup=str(prepared.destination_backup.path)
                if prepared.destination_backup
                else None,
            )
        except Exception as exc:
            try:
                self.history.append(
                    operation_id, "failed", farm=prepared.source.folder_id, error=str(exc)
                )
            except BridgeError:
                pass
            if verified:
                raise BridgeError(
                    "The destination was verified, but finalization failed. Inspect the farm "
                    f"and backups before retrying: {exc}"
                ) from exc
            if isinstance(exc, (BridgeError, OSError, ValueError)):
                raise
            raise BridgeError(f"Transfer failed: {exc}") from exc
        finally:
            shutil.rmtree(prepared.staged_source.parent, ignore_errors=True)

    def available_backups(self) -> list[BackupInfo]:
        archives: list[BackupInfo] = []
        for path in sorted(self.paths.backups.glob("*.zip"), reverse=True):
            try:
                archives.append(self.backups.verify(path))
            except BridgeError:
                continue
        return archives

    def prepare_restore(
        self,
        archive_path: Path,
        target_device: Device,
        progress: Progress = lambda _step: None,
    ) -> PreparedRestore:
        operation_id = uuid.uuid4().hex[:16]
        stage_root = self.paths.staging / operation_id
        self.history.append(
            operation_id, "starting_restore", archive=str(archive_path), target=target_device
        )
        try:
            ensure_game_closed()
            progress("Verifying selected backup")
            archive = self.backups.verify(archive_path)
            with self._restore_root(target_device) as target_root:
                current = _find(scan_root(target_root, target_device), archive.folder_id)
                target_path = target_root / archive.folder_id
                if current is None and (target_path.exists() or target_path.is_symlink()):
                    raise BridgeError(
                        "The restore target exists but is not a standard farm folder. "
                        "Inspect it before restoring."
                    )
                if current is not None and not current.valid:
                    raise BridgeError("The current farm is incomplete; inspect it before restoring")
                current_backup = None
                if current is not None:
                    progress("Backing up current farm")
                    current_backup = self.backups.create(current, operation_id)
                stage_root.mkdir(parents=True, exist_ok=False)
                staged_source = stage_root / archive.folder_id
                progress("Extracting and verifying backup")
                self.backups.extract(archive, staged_source)
            target_location = (
                str(self.mac_root / archive.folder_id)
                if target_device == "mac"
                else f"iPad File Sharing/Stardew Documents/{archive.folder_id}"
            )
            prepared = PreparedRestore(
                operation_id,
                archive,
                target_device,
                current,
                current_backup,
                staged_source,
                target_location,
            )
            self.history.append(
                operation_id,
                "prepared_restore",
                farm=archive.folder_id,
                target=target_device,
                archive=str(archive.path),
                destination_backup=str(current_backup.path) if current_backup else None,
            )
            return prepared
        except Exception as exc:
            shutil.rmtree(stage_root, ignore_errors=True)
            self.history.append(operation_id, "failed", error=str(exc))
            if isinstance(exc, (BridgeError, OSError, ValueError)):
                raise
            raise BridgeError(f"Could not prepare restore: {exc}") from exc

    def cancel_restore(self, prepared: PreparedRestore) -> None:
        self.history.append(prepared.operation_id, "cancelled", farm=prepared.archive.folder_id)
        shutil.rmtree(prepared.staged_source.parent, ignore_errors=True)

    def execute_restore(
        self, prepared: PreparedRestore, progress: Progress = lambda _step: None
    ) -> None:
        verified = False
        try:
            ensure_game_closed()
            self.backups.verify(prepared.archive.path)
            if prepared.destination_backup:
                self.backups.verify(prepared.destination_backup.path)
            if manifest_for(prepared.staged_source) != prepared.archive.manifest:
                raise BridgeError("Prepared backup changed before writing")
            progress("Rechecking destination farm")
            with self._restore_root(prepared.target_device) as target_root:
                current = _find(
                    scan_root(target_root, prepared.target_device), prepared.archive.folder_id
                )
                target_path = target_root / prepared.archive.folder_id
                if prepared.destination is None and (target_path.exists() or target_path.is_symlink()):
                    raise ChangedSaveError(
                        "A destination path appeared after backup. No write was made."
                    )
                if not _same_snapshot(prepared.destination, current):
                    raise ChangedSaveError("Destination changed after backup. No write was made.")
                self.history.append(
                    prepared.operation_id, "writing_restore", farm=prepared.archive.folder_id
                )
                progress(f"Restoring farm on {prepared.target_device.title()}")
                if prepared.target_device == "ipad":
                    self.usb.replace_verified(
                        prepared.archive.folder_id,
                        prepared.staged_source,
                        prepared.archive.manifest,
                        prepared.operation_id,
                        current.manifest if current else None,
                    )
                else:
                    replace_verified(
                        target_root / prepared.archive.folder_id,
                        prepared.staged_source,
                        prepared.archive.manifest,
                        prepared.operation_id,
                    )
                verified = True
            progress("Restored farm verified")
            self.history.append(
                prepared.operation_id,
                "restored",
                farm=prepared.archive.folder_id,
                target=prepared.target_device,
                archive=str(prepared.archive.path),
                destination_backup=str(prepared.destination_backup.path)
                if prepared.destination_backup
                else None,
            )
        except Exception as exc:
            try:
                self.history.append(
                    prepared.operation_id,
                    "failed",
                    farm=prepared.archive.folder_id,
                    error=str(exc),
                )
            except BridgeError:
                pass
            if verified:
                raise BridgeError(
                    "The restored farm was verified, but finalization failed. Inspect the farm "
                    f"and backups before retrying: {exc}"
                ) from exc
            if isinstance(exc, (BridgeError, OSError, ValueError)):
                raise
            raise BridgeError(f"Restore failed: {exc}") from exc
        finally:
            shutil.rmtree(prepared.staged_source.parent, ignore_errors=True)
