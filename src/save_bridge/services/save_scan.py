import hashlib
import json
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from save_bridge.models import Device, FarmSave, SaveFile, SaveManifest

MAX_METADATA_BYTES = 32 * 1024 * 1024
MAX_XML_BYTES = 512 * 1024 * 1024
SUPPLEMENTAL_SUFFIXES = ("_old", "_SVBAK", "_SVEMERG")


def manifest_for(folder: Path) -> SaveManifest:
    """Hash every regular file in a farm folder with a stable order."""
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError(f"Not a safe farm folder: {folder}")
    entries: list[SaveFile] = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"A save contains a link: {path.name}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"A save contains an unsupported item: {path.name}")
        relative = path.relative_to(folder).as_posix()
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise ValueError("Unsafe file path in save")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        entries.append(SaveFile(relative, path.stat().st_size, digest.hexdigest()))
    signature = hashlib.sha256()
    for entry in entries:
        signature.update(json.dumps([entry.relative_path, entry.byte_count, entry.sha256]).encode())
        signature.update(b"\n")
    return SaveManifest(tuple(entries), signature.hexdigest(), sum(x.byte_count for x in entries))


def _read_xml(path: Path) -> ElementTree.Element | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_METADATA_BYTES:
            return None
        return ElementTree.fromstring(path.read_bytes())
    except (OSError, ElementTree.ParseError, ValueError):
        return None


def _well_formed_xml(path: Path) -> bool:
    try:
        if path.stat().st_size > MAX_XML_BYTES:
            return False
        with path.open("rb") as stream:
            if b"<!DOCTYPE" in stream.read(4096).upper():
                return False
            stream.seek(0)
            for _event, element in ElementTree.iterparse(stream, events=("end",)):
                element.clear()
        return True
    except (OSError, ElementTree.ParseError, ValueError):
        return False


def _text(root: ElementTree.Element | None, *paths: str) -> str | None:
    if root is None:
        return None
    for path in paths:
        value = root.findtext(path)
        if value is not None and value.strip():
            return value.strip()
    return None


def _money(value: str | None) -> int | None:
    try:
        result = int(value) if value is not None else None
        return result if result is not None and result >= 0 else None
    except ValueError:
        return None


def scan_farm(folder: Path, device: Device) -> FarmSave:
    folder_id = folder.name
    primary = folder / folder_id
    info = folder / "SaveGameInfo"
    warnings: list[str] = []
    valid = (
        primary.is_file() and info.is_file() and not primary.is_symlink() and not info.is_symlink()
    )
    if not valid:
        warnings.append("Missing the main save file or SaveGameInfo")
    elif not _well_formed_xml(primary) or not _well_formed_xml(info):
        valid = False
        warnings.append("The main save or SaveGameInfo is malformed or too large to validate")
    for suffix in SUPPLEMENTAL_SUFFIXES:
        if (folder / f"{folder_id}{suffix}").exists():
            if suffix == "_SVEMERG":
                warnings.append(
                    "Contains an emergency save; only the standard save is transferable"
                )
            else:
                warnings.append(f"Contains {suffix} supplemental save")
    info_xml = _read_xml(info)
    main_xml = _read_xml(primary) if valid else None
    if valid and info_xml is None:
        warnings.append("SaveGameInfo metadata could not be read")
    farm_name = _text(info_xml, "farmName") or _text(main_xml, "player/farmName")
    if farm_name is None:
        farm_name = folder_id.rsplit("_", 1)[0]
    player = _text(info_xml, "name") or _text(main_xml, "player/name")
    money = _money(_text(info_xml, "money") or _text(main_xml, "player/money"))
    version = _text(info_xml, "gameVersion", "version") or _text(main_xml, "gameVersion")
    day = _text(main_xml, "dayOfMonth")
    season = _text(main_xml, "currentSeason")
    year = _text(main_xml, "year")
    in_game_date = f"{season.title()} {day}, Year {year}" if day and season and year else None
    manifest = None
    if valid:
        try:
            manifest = manifest_for(folder)
        except (OSError, ValueError) as exc:
            warnings.append(f"Could not verify all files: {exc}")
    try:
        times = [p.stat().st_mtime for p in (primary, info) if p.exists()]
        modified = datetime.fromtimestamp(
            max(times) if times else folder.stat().st_mtime
        ).astimezone()
    except OSError:
        modified = datetime.now().astimezone()
    return FarmSave(
        device=device,
        path=folder,
        folder_id=folder_id,
        farm_name=farm_name,
        player_name=player,
        money=money,
        in_game_date=in_game_date,
        game_version=version,
        modified_at=modified,
        manifest=manifest,
        warnings=tuple(warnings),
    )


def scan_root(root: Path, device: Device) -> tuple[FarmSave, ...]:
    if not root.exists():
        return ()
    if not root.is_dir():
        raise ValueError(f"Save location is not a folder: {root}")
    saves = [
        scan_farm(path, device)
        for path in root.iterdir()
        if path.is_dir() and not path.is_symlink() and not path.name.startswith(".bridge-")
    ]
    return tuple(sorted(saves, key=lambda s: (s.farm_name.casefold(), s.folder_id)))
