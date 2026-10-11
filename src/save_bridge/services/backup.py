import hashlib
import json
import os
import shutil
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from save_bridge.errors import BridgeError, OperationCancelled
from save_bridge.models import FarmSave, SaveFile, SaveManifest
from save_bridge.services.save_scan import manifest_for

MANIFEST_NAME = "bridge-manifest.json"


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    folder_id: str
    device: str
    manifest: SaveManifest
    created_at: str
    farm_name: str = ""


def _safe_relative(value: str) -> bool:
    parts = PurePosixPath(value).parts
    return (
        bool(parts) and not value.startswith("/") and all(part not in (".", "..") for part in parts)
    )


def _manifest_from_json(raw: dict) -> SaveManifest:
    files = tuple(
        SaveFile(str(x["relative_path"]), int(x["byte_count"]), str(x["sha256"]))
        for x in raw["files"]
    )
    if any(not _safe_relative(x.relative_path) for x in files):
        raise BridgeError("Backup contains an unsafe file path")
    if len({x.relative_path for x in files}) != len(files):
        raise BridgeError("Backup contains duplicate file paths")
    aggregate = hashlib.sha256()
    for item in files:
        aggregate.update(json.dumps([item.relative_path, item.byte_count, item.sha256]).encode())
        aggregate.update(b"\n")
    if aggregate.hexdigest() != raw["aggregate_sha256"]:
        raise BridgeError("Backup manifest checksum is invalid")
    total = sum(x.byte_count for x in files)
    if total != int(raw["total_bytes"]):
        raise BridgeError("Backup manifest size is invalid")
    return SaveManifest(files, aggregate.hexdigest(), total)


class BackupService:
    def __init__(self, root: Path) -> None:
        self.root = root

    def create(
        self, save: FarmSave, operation_id: str, cancelled: Callable[[], bool] = lambda: False
    ) -> BackupInfo:
        if not save.valid or save.manifest is None:
            raise BridgeError(f"Cannot back up an invalid farm: {save.folder_id}")
        self.root.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(self.root).free
        if free < save.manifest.total_bytes + 16 * 1024 * 1024:
            raise BridgeError("Not enough free Mac storage for a verified backup")
        filename = f"{operation_id}-{save.device}-{save.folder_id}.zip"
        path = self.root / filename
        temp = self.root / f".{filename}.{uuid.uuid4().hex}.tmp"
        created = datetime.now(UTC).isoformat()
        payload = {
            "format": 1,
            "folder_id": save.folder_id,
            "farm_name": save.farm_name,
            "device": save.device,
            "created_at": created,
            "aggregate_sha256": save.manifest.aggregate_sha256,
            "total_bytes": save.manifest.total_bytes,
            "files": [vars(item) for item in save.manifest.files],
        }
        try:
            with zipfile.ZipFile(
                temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as archive:
                archive.writestr(MANIFEST_NAME, json.dumps(payload, sort_keys=True))
                for item in save.manifest.files:
                    if cancelled():
                        raise OperationCancelled("Backup cancelled before any destination write")
                    archive.write(save.path / item.relative_path, f"files/{item.relative_path}")
            with temp.open("rb") as stream:
                os.fsync(stream.fileno())
            self.verify(temp)
            os.replace(temp, path)
            return BackupInfo(path, save.folder_id, save.device, save.manifest, created, save.farm_name)
        except (OSError, zipfile.BadZipFile, ValueError) as exc:
            raise BridgeError(f"Could not create a verified backup: {exc}") from exc
        finally:
            temp.unlink(missing_ok=True)

    @staticmethod
    def verify(path: Path) -> BackupInfo:
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)) or MANIFEST_NAME not in names:
                    raise BridgeError("Backup is missing its manifest or contains duplicate files")
                raw = json.loads(archive.read(MANIFEST_NAME))
                if raw.get("format") != 1:
                    raise BridgeError("Unsupported backup format")
                folder_id = str(raw["folder_id"])
                if not folder_id or Path(folder_id).name != folder_id or folder_id in (".", ".."):
                    raise BridgeError("Backup has an unsafe farm folder name")
                manifest = _manifest_from_json(raw)
                expected = {f"files/{x.relative_path}" for x in manifest.files}
                if set(names) != expected | {MANIFEST_NAME}:
                    raise BridgeError("Backup files do not match its manifest")
                for item in manifest.files:
                    digest = hashlib.sha256()
                    size = 0
                    with archive.open(f"files/{item.relative_path}") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(chunk)
                            size += len(chunk)
                    if digest.hexdigest() != item.sha256 or size != item.byte_count:
                        raise BridgeError(f"Backup verification failed for {item.relative_path}")
                return BackupInfo(
                    path,
                    folder_id,
                    str(raw["device"]),
                    manifest,
                    str(raw["created_at"]),
                    str(raw.get("farm_name") or folder_id.rsplit("_", 1)[0]),
                )
        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            zipfile.BadZipFile,
            json.JSONDecodeError,
        ) as exc:
            raise BridgeError(f"Cannot verify backup {path.name}: {exc}") from exc

    @staticmethod
    def extract(backup: BackupInfo, destination: Path) -> None:
        checked = BackupService.verify(backup.path)
        if checked.manifest != backup.manifest:
            raise BridgeError("Backup changed since it was selected")
        destination.mkdir(parents=True, exist_ok=False)
        with zipfile.ZipFile(backup.path) as archive:
            for item in backup.manifest.files:
                target = destination / item.relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                with (
                    archive.open(f"files/{item.relative_path}") as source,
                    target.open("wb") as output,
                ):
                    shutil.copyfileobj(source, output)
        if manifest_for(destination) != backup.manifest:
            raise BridgeError("Extracted backup did not pass verification")
