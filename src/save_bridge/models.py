from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

Device = Literal["mac", "ipad"]


def device_label(device: str) -> str:
    return "iPad" if device == "ipad" else "Mac"


@dataclass(frozen=True)
class SaveFile:
    relative_path: str
    byte_count: int
    sha256: str


@dataclass(frozen=True)
class SaveManifest:
    files: tuple[SaveFile, ...]
    aggregate_sha256: str
    total_bytes: int

    @property
    def file_count(self) -> int:
        return len(self.files)


@dataclass(frozen=True)
class FarmSave:
    device: Device
    path: Path
    folder_id: str
    farm_name: str
    player_name: str | None
    money: int | None
    in_game_date: str | None
    game_version: str | None
    modified_at: datetime
    manifest: SaveManifest | None
    warnings: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.manifest is not None


@dataclass(frozen=True)
class ScanResult:
    mac_saves: tuple[FarmSave, ...]
    ipad_saves: tuple[FarmSave, ...]
    ipad_status: str
    ipad_device_name: str | None = None
