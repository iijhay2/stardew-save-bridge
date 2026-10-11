"""Read-only check of the USB prerequisites and Stardew File Sharing visibility."""

from pathlib import Path

from save_bridge.app_paths import AppPaths
from save_bridge.errors import DeviceUnavailableError
from save_bridge.services.ipad import USBBridge, resolve_tool


def main() -> None:
    for tool in ("idevice_id", "ideviceinfo", "ifuse"):
        path = resolve_tool(tool)
        print(f"{tool}: {path or 'missing'}")
    bridge = USBBridge(AppPaths.default().staging)
    try:
        device_id = bridge.device_id()
        print(f"USB iPad: {bridge.device_name(device_id)}")
        print(f"Stardew shared app ID: {bridge.stardew_app_id(device_id)}")
        with bridge.mounted_documents() as (root, _name, _app_id):
            folders = [p.name for p in Path(root).iterdir() if p.is_dir()]
            print(f"Shared Documents mounted; {len(folders)} folders visible")
            for folder in folders:
                print(f"  {folder}")
        print("Read-only USB check passed; Documents unmounted")
    except DeviceUnavailableError as exc:
        print(f"USB check blocked: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
