import argparse
import sys
from importlib.resources import files

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from save_bridge import __version__
from save_bridge.ui.window import BridgeWindow


def create_application() -> QApplication:
    existing = QApplication.instance()
    if existing is not None and not isinstance(existing, QApplication):
        raise RuntimeError("A non-GUI Qt application is already running")
    app = existing if existing is not None else QApplication(sys.argv)
    app.setApplicationName("Stardew Save Bridge")
    app.setOrganizationName("Stardew Save Bridge")
    app.setWindowIcon(QIcon(str(files("save_bridge").joinpath("resources/flower.svg"))))
    style = files("save_bridge").joinpath("resources/styles.qss").read_text(encoding="utf-8")
    app.setStyleSheet(style)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Stardew Save Bridge")
    parser.add_argument("--version", action="version", version=__version__)
    parser.parse_args()
    app = create_application()
    window = BridgeWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
