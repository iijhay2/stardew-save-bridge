"""Direct USB access to one app's File Sharing Documents through AFC."""

import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from save_bridge.errors import BridgeError, ChangedSaveError, DeviceUnavailableError
from save_bridge.models import SaveManifest
from save_bridge.services.save_scan import manifest_for

TOOL_DIRECTORIES = (Path("/opt/homebrew/bin"), Path("/usr/local/bin"), Path("/opt/local/bin"))
FARM_FOLDER = re.compile(r"[^./\\\r\n][^/\\\r\n]*_[0-9]+\Z")


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


class USBBridge:
    def __init__(self, staging_root: Path) -> None:
        self.staging_root = staging_root

    @staticmethod
    def _run(command: list[str], timeout: int = 30) -> str:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DeviceUnavailableError(f"Could not run {Path(command[0]).name}: {exc}") from exc
        detail = (result.stderr or result.stdout).strip()
        # afcclient 1.4.0 sometimes exits zero after an AFC command fails.
        if result.returncode or any(
            line.lstrip().startswith(("Error:", "afcclient:"))
            for line in (result.stdout + "\n" + result.stderr).splitlines()
        ):
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
        tool = resolve_tool("ideviceinstaller")
        if not tool:
            raise DeviceUnavailableError("Install ideviceinstaller to find Stardew Valley")
        output = self._run([tool, "--udid", device_id, "list", "--xml"], timeout=45)
        try:
            installed = plistlib.loads(output.encode())
            candidates = [
                app["CFBundleIdentifier"]
                for app in installed
                if isinstance(app, dict)
                and app.get("UIFileSharingEnabled") is True
                and "stardew" in str(app).casefold()
            ]
        except (ValueError, TypeError, KeyError, plistlib.InvalidFileException) as exc:
            raise DeviceUnavailableError("Could not read the iPad app list") from exc
        if len(candidates) != 1:
            raise DeviceUnavailableError(
                "Stardew Valley is not uniquely visible in iPad File Sharing. "
                "Check Files/Finder sharing on the connected iPad."
            )
        return candidates[0]

    def _afc(self, device_id: str, app_id: str, *args: str, timeout: int = 120) -> str:
        tool = resolve_tool("afcclient")
        if not tool:
            raise DeviceUnavailableError("Install libimobiledevice; afcclient is required")
        return self._run(
            [tool, "--udid", device_id, "--documents", app_id, "--", *args], timeout=timeout
        )

    def _remote_info(self, device_id: str, app_id: str, path: str) -> dict | None:
        try:
            return json.loads(self._afc(device_id, app_id, "info", path))
        except DeviceUnavailableError as exc:
            if "Not found (8)" in str(exc):
                return None
            raise
        except (ValueError, TypeError) as exc:
            raise DeviceUnavailableError("Unexpected iPad file information") from exc

    @contextmanager
    def mounted_documents(self) -> Iterator[tuple[Path, str, str]]:
        """Read a temporary local snapshot; no filesystem driver or iPad write."""
        device_id = self.device_id()
        name = self.device_name(device_id)
        app_id = self.stardew_app_id(device_id)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="ipad-snapshot-", dir=self.staging_root))
        try:
            entries = self._afc(device_id, app_id, "ls", "/Documents", timeout=45)
            for folder in entries.splitlines():
                if FARM_FOLDER.fullmatch(folder):
                    remote = f"/Documents/{folder}"
                    info = self._remote_info(device_id, app_id, remote)
                    if info and info.get("st_ifmt") == "S_IFDIR":
                        self._afc(device_id, app_id, "get", "-r", remote, str(root), timeout=180)
            yield root, name, app_id
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def replace_verified(
        self,
        folder_id: str,
        staged_source: Path,
        expected: SaveManifest,
        operation_id: str,
        old_manifest: SaveManifest | None,
    ) -> None:
        """Upload, read back, swap, and verify one farm over AFC."""
        if not FARM_FOLDER.fullmatch(folder_id) or staged_source.name != folder_id:
            raise BridgeError("Unsafe farm folder name")
        if manifest_for(staged_source) != expected:
            raise ChangedSaveError("Prepared farm changed before the iPad write")
        device_id = self.device_id()
        app_id = self.stardew_app_id(device_id)
        target = f"/Documents/{folder_id}"
        incoming = f"/Documents/.bridge-incoming-{operation_id}"
        previous = f"/Documents/.bridge-previous-{operation_id}"
        self.staging_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="ipad-verify-", dir=self.staging_root) as temp:
            verify_root = Path(temp)
            current = self._remote_info(device_id, app_id, target)
            if (current is None) != (old_manifest is None):
                raise ChangedSaveError("The iPad farm changed before the write")
            if current:
                self._afc(device_id, app_id, "get", "-r", target, str(verify_root), timeout=180)
                if manifest_for(verify_root / folder_id) != old_manifest:
                    raise ChangedSaveError("The iPad farm changed before the write")
                shutil.rmtree(verify_root / folder_id)
            if self._remote_info(device_id, app_id, incoming) or self._remote_info(
                device_id, app_id, previous
            ):
                raise BridgeError("A prior iPad transfer stage needs inspection before retrying")
            moved_old = False
            swapped = False
            try:
                self._afc(
                    device_id, app_id, "put", "-r", str(staged_source), incoming, timeout=180
                )
                self._afc(device_id, app_id, "get", "-r", incoming, str(verify_root), timeout=180)
                if manifest_for(verify_root / Path(incoming).name) != expected:
                    raise BridgeError("The uploaded iPad copy differs from the source")
                shutil.rmtree(verify_root / Path(incoming).name)
                if current:
                    self._afc(device_id, app_id, "mv", target, previous)
                    moved_old = True
                self._afc(device_id, app_id, "mv", incoming, target)
                swapped = True
                self._afc(device_id, app_id, "get", "-r", target, str(verify_root), timeout=180)
                if manifest_for(verify_root / folder_id) != expected:
                    raise BridgeError("iPad verification failed after the write")
                if moved_old:
                    self._afc(device_id, app_id, "rm", "-rf", previous)
            except Exception as exc:
                if moved_old:
                    try:
                        if swapped:
                            self._afc(device_id, app_id, "rm", "-rf", target)
                        self._afc(device_id, app_id, "mv", previous, target)
                    except DeviceUnavailableError as restore_exc:
                        raise BridgeError(
                            "iPad transfer failed and automatic restoration was interrupted. "
                            f"Use the verified backup in History: {restore_exc}"
                        ) from exc
                elif swapped:
                    self._afc(device_id, app_id, "rm", "-rf", target)
                raise BridgeError(f"iPad transfer failed: {exc}") from exc
            finally:
                if not swapped:
                    try:
                        self._afc(device_id, app_id, "rm", "-rf", incoming)
                    except DeviceUnavailableError:
                        pass
