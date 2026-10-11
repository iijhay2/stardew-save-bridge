import csv
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from save_bridge.errors import DeviceUnavailableError

TOOL_DIRECTORIES = (Path("/opt/homebrew/bin"), Path("/usr/local/bin"), Path("/opt/local/bin"))


def resolve_tool(name: str) -> str | None:
    """Finder apps do not inherit the user's interactive shell PATH."""
    found = shutil.which(name)
    if found:
        return found
    for directory in TOOL_DIRECTORIES:
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def parse_shared_apps(output: str) -> list[tuple[str, str]]:
    apps: list[tuple[str, str]] = []
    for line in output.splitlines():
        try:
            cells = next(csv.reader([line], skipinitialspace=True))
        except (csv.Error, StopIteration):
            continue
        if len(cells) >= 3 and "." in cells[0]:
            apps.append((cells[0].strip(), cells[-1].strip()))
    return apps


class USBBridge:
    def __init__(self, staging_root: Path) -> None:
        self.staging_root = staging_root

    @staticmethod
    def _run(command: list[str], timeout: int = 20) -> str:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DeviceUnavailableError(f"Could not run {Path(command[0]).name}: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise DeviceUnavailableError(detail or f"{Path(command[0]).name} failed")
        return result.stdout

    def device_id(self) -> str:
        tool = resolve_tool("idevice_id")
        if not tool:
            raise DeviceUnavailableError("Install libimobiledevice to detect your iPad")
        devices = [x.strip() for x in self._run([tool, "--list"]).splitlines() if x.strip()]
        if not devices:
            raise DeviceUnavailableError("Connect an unlocked iPad with a USB cable")
        if len(devices) != 1:
            raise DeviceUnavailableError("Connect only one iPad before transferring a farm")
        return devices[0]

    def device_name(self, device_id: str) -> str:
        tool = resolve_tool("ideviceinfo")
        if not tool:
            raise DeviceUnavailableError("Install libimobiledevice to read iPad trust status")
        try:
            return self._run([tool, "--udid", device_id, "--key", "DeviceName"]).strip()
        except DeviceUnavailableError as exc:
            raise DeviceUnavailableError(
                "Unlock the iPad and tap Trust This Computer, then refresh"
            ) from exc

    def stardew_app_id(self, device_id: str) -> str:
        tool = resolve_tool("ifuse")
        if not tool:
            raise DeviceUnavailableError(
                "Install ifuse and macFUSE to read Stardew's shared Documents folder"
            )
        output = self._run([tool, "--list-apps", "--udid", device_id], timeout=40)
        candidates = [
            app_id
            for app_id, name in parse_shared_apps(output)
            if "stardew" in name.casefold() or "stardew" in app_id.casefold()
        ]
        if len(candidates) != 1:
            raise DeviceUnavailableError(
                "Stardew Valley is not uniquely visible in iPad File Sharing. "
                "Check Files/Finder sharing on the connected iPad."
            )
        return candidates[0]

    @contextmanager
    def mounted_documents(self) -> Iterator[tuple[Path, str, str]]:
        device_id = self.device_id()
        name = self.device_name(device_id)
        app_id = self.stardew_app_id(device_id)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        mountpoint = Path(tempfile.mkdtemp(prefix="ipad-", dir=self.staging_root))
        mounted = False
        try:
            tool = resolve_tool("ifuse")
            if not tool:
                raise DeviceUnavailableError("ifuse is no longer available")
            self._run(
                [tool, "--documents", app_id, str(mountpoint), "--udid", device_id], timeout=45
            )
            mounted = True
            yield mountpoint, name, app_id
        finally:
            if mounted:
                try:
                    self._run(["/sbin/umount", str(mountpoint)], timeout=20)
                except DeviceUnavailableError as exc:
                    raise DeviceUnavailableError(
                        f"Could not unmount iPad Documents safely: {exc}"
                    ) from exc
            try:
                mountpoint.rmdir()
            except OSError:
                pass
