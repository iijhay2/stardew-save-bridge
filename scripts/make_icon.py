"""Draw the original farm-journal icon and assemble a macOS .icns file."""

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen


def draw_base() -> QImage:
    image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#4F6B56"), 22))
    painter.setBrush(QColor("#FEFAF3"))
    painter.drawRoundedRect(72, 72, 880, 880, 180, 180)
    painter.setPen(QPen(QColor("#84A282"), 12))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(101, 101, 822, 822, 150, 150)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    blocks = [
        (7, 10, 2, 5, "#4F6B56"),
        (5, 12, 2, 2, "#84A282"),
        (9, 11, 2, 2, "#84A282"),
        (6, 1, 4, 3, "#D9A2B5"),
        (3, 4, 4, 4, "#F6E2E9"),
        (9, 4, 4, 4, "#F6E2E9"),
        (6, 8, 4, 3, "#D9A2B5"),
        (6, 4, 4, 4, "#8E5364"),
        (7, 5, 2, 2, "#FEFAF3"),
    ]
    for x, y, width, height, color in blocks:
        painter.fillRect(100 + x * 52, 95 + y * 52, width * 52, height * 52, QColor(color))
    painter.end()
    return image


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/farm-journal.icns")
    output.parent.mkdir(parents=True, exist_ok=True)
    iconset = output.parent / "farm-journal.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    image = draw_base()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            pixels = size * scale
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            image.scaled(
                pixels,
                pixels,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ).save(str(iconset / name))
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(output)], check=True)
    print(output)


if __name__ == "__main__":
    main()
