from datetime import datetime

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
)

from save_bridge.models import FarmSave

MAC_MONEY_ROLE = Qt.ItemDataRole.UserRole.value + 1
IPAD_MONEY_ROLE = Qt.ItemDataRole.UserRole.value + 2


def flower_pixmap() -> QPixmap:
    """An original tiny pixel flower that needs no image plugin."""
    pixels = [
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
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    for x, y, width, height, color in pixels:
        painter.fillRect(x * 3, y * 3, width * 3, height * 3, QColor(color))
    painter.end()
    return pixmap


class FarmItemDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect = option.rect.adjusted(2, 3, -6, -7)
        painter.fillRect(rect.translated(4, 4), QColor("#84A282"))
        painter.fillRect(rect, QColor("#B8CFB3" if selected else "#FEFAF3"))
        painter.setPen(QColor("#4F6B56"))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.setPen(QColor("#4F6B56"))
        flower = flower_pixmap()
        painter.drawPixmap(rect.left() + 12, rect.top() + 13, flower.scaled(27, 27))
        title_x = rect.left() + 47
        painter.setPen(QColor("#2F4638"))
        painter.setFont(QFont("Avenir Next", 13, QFont.Weight.DemiBold))
        available = max(40, rect.right() - title_x - 9)
        title = painter.fontMetrics().elidedText(
            str(index.data(Qt.ItemDataRole.DisplayRole)), Qt.TextElideMode.ElideRight, available
        )
        painter.drawText(title_x, rect.top() + 25, title)
        painter.setPen(QColor("#3F5544"))
        painter.setFont(QFont("Avenir Next", 9))
        mac_line = painter.fontMetrics().elidedText(
            f"Mac: {index.data(MAC_MONEY_ROLE)}", Qt.TextElideMode.ElideRight, available
        )
        ipad_line = painter.fontMetrics().elidedText(
            f"iPad: {index.data(IPAD_MONEY_ROLE)}", Qt.TextElideMode.ElideRight, available
        )
        painter.drawText(title_x, rect.top() + 45, mac_line)
        painter.drawText(title_x, rect.top() + 62, ipad_line)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(0, 88)


def plain_label(text: str, object_name: str | None = None) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if object_name:
        widget.setObjectName(object_name)
    return widget


def money_text(money: int | None) -> str:
    return f"{money:,}g" if money is not None else "Money unavailable"


def date_text(value: datetime) -> str:
    return value.strftime("%b %-d, %Y · %I:%M %p")


class CopyCard(QFrame):
    def __init__(self, device: str) -> None:
        super().__init__()
        self.setObjectName("CopyCard")
        self.device = device
        self.save: FarmSave | None = None
        self.setMinimumWidth(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(19, 19, 19, 18)
        layout.setSpacing(10)
        top = QHBoxLayout()
        self.device_label = plain_label("ON YOUR MAC" if device == "mac" else "ON YOUR IPAD", "Eyebrow")
        self.status_label = plain_label("", "StatusWarn")
        self.status_label.setMinimumHeight(27)
        top.addWidget(self.device_label)
        top.addStretch()
        top.addWidget(self.status_label)
        layout.addLayout(top)
        self.farm_label = plain_label("No copy of this farm", "FarmTitle")
        layout.addWidget(self.farm_label)
        self.money_label = plain_label("", "Money")
        layout.addWidget(self.money_label)
        self.radio = QRadioButton(f"Use the {'Mac' if device == 'mac' else 'iPad'} copy")
        self.radio.setAccessibleName(f"Use the {device} copy of this farm")
        layout.addWidget(self.radio)
        self.player_label = plain_label("", "Muted")
        self.date_label = plain_label("", "Muted")
        self.modified_label = plain_label("", "Muted")
        layout.addWidget(self.player_label)
        layout.addWidget(self.date_label)
        layout.addWidget(self.modified_label)
        self.warning_label = plain_label("", "Warning")
        layout.addWidget(self.warning_label)
        layout.addStretch()
        self.update_save(None)

    def update_save(self, save: FarmSave | None) -> None:
        self.save = save
        if save is None:
            self.farm_label.setText("No copy of this farm")
            self.money_label.setText("A new copy can be made here")
            self.player_label.setText("")
            self.date_label.setText("")
            self.modified_label.setText("")
            self.warning_label.hide()
            self.status_label.setObjectName("StatusWarn")
            self.status_label.setText("Empty")
            self.radio.setEnabled(False)
        else:
            self.farm_label.setText(f"{save.farm_name} Farm")
            self.money_label.setText(money_text(save.money))
            self.player_label.setText(f"Farmer: {save.player_name or 'Unavailable'}")
            self.date_label.setText(f"In game: {save.in_game_date or 'Date unavailable'}")
            self.modified_label.setText(f"Saved: {date_text(save.modified_at)}")
            self.warning_label.setText(
                "This copy needs attention. Open it in Stardew Valley and save again."
                if not save.valid else ""
            )
            self.warning_label.setVisible(not save.valid)
            self.status_label.setObjectName("StatusGood" if save.valid else "StatusWarn")
            self.status_label.setText("Ready" if save.valid else "Needs attention")
            self.radio.setEnabled(save.valid)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def show_unavailable(self, reason: str) -> None:
        self.update_save(None)
        self.farm_label.setText("iPad copy unavailable")
        self.money_label.setText("Connect your iPad to see this copy")
        self.status_label.setText("Not connected")
        self.warning_label.setText(reason)
        self.warning_label.show()

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
