from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from save_bridge.models import Device, device_label
from save_bridge.services.backup import BackupInfo
from save_bridge.services.bridge import PreparedRestore, PreparedTransfer
from save_bridge.ui.components import plain_label


class ProgressDialog(QDialog):
    def __init__(self, title: str, can_cancel: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(plain_label(title, "SectionTitle"))
        self.step = plain_label("Starting…", "Muted")
        layout.addWidget(self.step)
        bar = QProgressBar()
        bar.setRange(0, 0)
        layout.addWidget(bar)
        self.note = plain_label(
            "Keep your iPad connected and leave Stardew Valley closed.", "Muted"
        )
        layout.addWidget(self.note)
        self.cancel_button = QPushButton("Cancel preparation")
        self.cancel_button.setVisible(can_cancel)
        layout.addWidget(self.cancel_button, alignment=Qt.AlignmentFlag.AlignRight)

    def set_step(self, value: str) -> None:
        self.step.setText(value)

    def request_cancel(self) -> None:
        self.cancel_button.setEnabled(False)
        self.step.setText("Cancelling safely…")

    def reject(self) -> None:
        # The worker finishes and closes this dialog after its cleanup has run.
        if self.cancel_button.isVisible() and self.cancel_button.isEnabled():
            self.cancel_button.click()


class ConfirmationDialog(QDialog):
    def __init__(self, prepared: PreparedTransfer | PreparedRestore, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm farm copy")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 27, 28, 25)
        layout.setSpacing(13)
        layout.addWidget(plain_label("ONE LAST LOOK", "Eyebrow"))
        if isinstance(prepared, PreparedTransfer):
            source = device_label(prepared.source.device)
            target = device_label(prepared.target_device)
            title = f"Copy {prepared.source.farm_name} Farm?"
            route = f"From your {source} to your {target}"
            effect = (
                f"The {target} copy will be replaced with the {source} copy."
                if prepared.destination
                else f"A new copy will be added to your {target}."
            )
            backups = (
                "Both copies have been backed up on this Mac. You can restore the earlier copy later."
                if prepared.destination_backup
                else "Your chosen copy has been backed up on this Mac."
            )
        else:
            target = device_label(prepared.target_device)
            title = f"Restore {prepared.archive.farm_name} Farm?"
            route = f"From your backup to your {target}"
            effect = (
                f"The current {target} copy will be replaced with this backup."
                if prepared.destination
                else f"A new copy will be added to your {target}."
            )
            backups = (
                "The current copy has been backed up on this Mac, in case you want it back."
                if prepared.destination_backup
                else "This will add the farm without replacing another copy."
            )
        layout.addWidget(plain_label(title, "PageTitle"))
        layout.addWidget(plain_label(route, "SectionTitle"))
        replacing = prepared.destination is not None
        layout.addWidget(plain_label(effect, "Danger" if replacing else "Warning"))
        layout.addWidget(plain_label(backups, "Muted"))
        layout.addWidget(
            plain_label("Make sure Stardew Valley is up to date on both devices.", "Muted")
        )
        acknowledgement = (
            "Stardew Valley is closed on my Mac, and this is the farm I want."
            if isinstance(prepared, PreparedRestore) and prepared.target_device == "mac"
            else "Stardew Valley is closed on both devices, and this is the farm I want."
        )
        self.acknowledge = QCheckBox(acknowledgement)
        layout.addWidget(self.acknowledge)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.confirm = QPushButton(f"Replace {target} copy" if replacing else f"Copy to {target}")
        self.confirm.setObjectName("DangerButton" if replacing else "Primary")
        self.confirm.setEnabled(False)
        self.acknowledge.toggled.connect(self.confirm.setEnabled)
        self.confirm.clicked.connect(self.accept)
        buttons.addWidget(self.confirm)
        layout.addLayout(buttons)


class HistoryDialog(QDialog):
    def __init__(self, backups: list[BackupInfo], history: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Your farm backups")
        self.setMinimumSize(500, 420)
        self.backups = backups
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(plain_label("Your farm backups", "PageTitle"))
        layout.addWidget(
            plain_label(
                "Choose an earlier copy if you want to bring a farm back.", "Muted"
            )
        )
        layout.addWidget(plain_label("Saved copies", "SectionTitle"))
        self.backup_list = QListWidget()
        for backup in backups:
            try:
                when = datetime.fromisoformat(backup.created_at).strftime("%b %d, %Y · %I:%M %p")
            except ValueError:
                when = "Earlier copy"
            item = QListWidgetItem(
                f"{backup.farm_name} Farm  ·  {device_label(backup.device)}\n{when}"
            )
            item.setData(Qt.ItemDataRole.UserRole, str(backup.path))
            self.backup_list.addItem(item)
        layout.addWidget(self.backup_list, 2)
        if not backups:
            layout.addWidget(plain_label("Your farm backups will appear here after a transfer.", "Muted"))
        target_row = QHBoxLayout()
        target_row.addWidget(plain_label("Restore to:"))
        self.target = QComboBox()
        self.target.addItem("Mac", "mac")
        self.target.addItem("iPad", "ipad")
        target_row.addWidget(self.target)
        self.restore_button = QPushButton("Continue to restore")
        self.restore_button.setObjectName("DangerButton")
        self.restore_button.setEnabled(False)
        self.backup_list.currentRowChanged.connect(
            lambda row: self.restore_button.setEnabled(row >= 0)
        )
        target_row.addStretch()
        target_row.addWidget(self.restore_button)
        layout.addLayout(target_row)
        layout.addWidget(plain_label("Recent activity", "SectionTitle"))
        operations = QListWidget()
        names = {backup.folder_id: backup.farm_name for backup in backups}
        descriptions = {
            "succeeded": "Copied",
            "restored": "Restored",
            "failed": "Stopped without finishing",
            "cancelled": "Cancelled",
        }
        for event in history:
            status = str(event.get("status", ""))
            if status not in descriptions:
                continue
            farm = names.get(str(event.get("farm", "")), "Farm")
            operations.addItem(
                f"{descriptions[status]} {farm} Farm  ·  {str(event.get('at', ''))[:10]}"
            )
        layout.addWidget(operations, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)

    def selected_restore(self) -> tuple[Path, Device] | None:
        item = self.backup_list.currentItem()
        if item is None:
            return None
        return Path(item.data(Qt.ItemDataRole.UserRole)), self.target.currentData()
