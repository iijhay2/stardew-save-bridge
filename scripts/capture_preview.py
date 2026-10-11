"""Render the journal with disposable sample farms for visual review."""

import argparse
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QTimer

from save_bridge.app_paths import AppPaths
from save_bridge.errors import DeviceUnavailableError
from save_bridge.main import create_application
from save_bridge.services.bridge import BridgeService
from save_bridge.ui.window import BridgeWindow


class PreviewUSB:
    def __init__(self, root: Path, disconnected: bool = False) -> None:
        self.root = root
        self.disconnected = disconnected

    @contextmanager
    def mounted_documents(self):
        if self.disconnected:
            raise DeviceUnavailableError(
                "Connect an unlocked iPad with a USB cable to compare farms."
            )
        yield self.root, "Preview iPad", "preview.stardew"


def make_farm(root: Path, folder: str, money: int) -> None:
    path = root / folder
    path.mkdir()
    name = folder.split("_")[0]
    (path / "SaveGameInfo").write_text(
        f"<Farmer><name>Robin</name><farmName>{name}</farmName>"
        f"<money>{money}</money><gameVersion>1.6.15</gameVersion></Farmer>"
    )
    (path / folder).write_text(
        "<SaveGame><player><name>Robin</name></player>"
        "<dayOfMonth>14</dayOfMonth><currentSeason>fall</currentSeason>"
        "<year>3</year></SaveGame>"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1150)
    parser.add_argument("--height", type=int, default=760)
    parser.add_argument("--empty", action="store_true")
    parser.add_argument("--disconnected", action="store_true")
    args = parser.parse_args()
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        mac = root / "mac"
        ipad = root / "ipad"
        mac.mkdir()
        ipad.mkdir()
        if not args.empty:
            make_farm(mac, "Bluebell_123", 123456)
            make_farm(mac, "Moss_456", 4521)
            make_farm(ipad, "Bluebell_123", 98765)
        app = create_application()
        window = BridgeWindow(
            BridgeService(AppPaths(root / "app"), mac, PreviewUSB(ipad, args.disconnected))
        )
        window.resize(args.width, args.height)
        window.show()

        def capture() -> None:
            if window.farms.count():
                window.farms.setCurrentRow(0)
                window.mac_card.radio.setChecked(True)
            app.processEvents()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(args.output))
            app.quit()

        QTimer.singleShot(700, capture)
        app.exec()


if __name__ == "__main__":
    main()
