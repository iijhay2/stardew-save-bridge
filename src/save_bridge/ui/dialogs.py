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

from save_bridge.models import Device
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
        self.setWindowTitle("Review the exact change")
        self.setMinimumWidth(565)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 27, 28, 25)
        layout.setSpacing(13)
        layout.addWidget(plain_label("One last look", "Eyebrow"))
        layout.addWidget(plain_label("Review the farm transfer", "PageTitle"))
        if isinstance(prepared, PreparedTransfer):
            source = prepared.source.device.title()
            target = prepared.target_device.title()
            title = f"{prepared.source.farm_name} Farm: {source} → {target}"
            effect = (
                f"This will replace the existing {target} copy."
                if prepared.destination
                else f"This will create a new copy on {target}."
            )
            backups = f"Source backup: {prepared.source_backup.path}"
            if prepared.destination_backup:
                backups += f"\nDestination backup: {prepared.destination_backup.path}"
            else:
                backups += "\nDestination was empty; there is no previous folder to back up."
            warning = prepared.warning
            file_count = prepared.source.manifest.file_count if prepared.source.manifest else 0
            source_path = prepared.source_location
            target_path = prepared.target_location
        else:
            target = prepared.target_device.title()
            title = f"Restore {prepared.archive.folder_id} on {target}"
            effect = (
                f"This will replace the existing {target} copy."
                if prepared.destination
                else f"This will create the farm on {target}."
            )
            backups = f"Selected archive: {prepared.archive.path}"
            if prepared.destination_backup:
                backups += f"\nCurrent farm backup: {prepared.destination_backup.path}"
            else:
                backups += "\nDestination was empty; there is no previous folder to back up."
            warning = None
            file_count = prepared.archive.manifest.file_count
            source_path = str(prepared.archive.path)
            target_path = prepared.target_location
        layout.addWidget(plain_label(title, "SectionTitle"))
        layout.addWidget(plain_label(effect, "Danger" if "replace" in effect else "Warning"))
        layout.addWidget(
            plain_label(
                f"Source: {source_path}\nTarget: {target_path}\nFiles: {file_count}", "Muted"
            )
        )
        if warning:
            layout.addWidget(plain_label(warning, "Warning"))
        backup_label = plain_label(backups, "Muted")
        backup_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(backup_label)
        acknowledgement = (
            "I checked the destination and closed Stardew Valley on my Mac."
            if isinstance(prepared, PreparedRestore) and prepared.target_device == "mac"
            else "I checked the destination and closed Stardew Valley on both devices."
        )
        self.acknowledge = QCheckBox(acknowledgement)
        layout.addWidget(self.acknowledge)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.confirm = QPushButton("Replace farm" if "replace" in effect else "Create farm copy")
        self.confirm.setObjectName("DangerButton" if "replace" in effect else "Primary")
        self.confirm.setEnabled(False)
        self.acknowledge.toggled.connect(self.confirm.setEnabled)
        self.confirm.clicked.connect(self.accept)
        buttons.addWidget(self.confirm)
        layout.addLayout(buttons)


class HistoryDialog(QDialog):
    def __init__(self, backups: list[BackupInfo], history: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Backups & history")
        self.setMinimumSize(660, 500)
        self.backups = backups
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(plain_label("Backups & history", "PageTitle"))
        layout.addWidget(
            plain_label(
                "Verified archives stay on this Mac until you delete them manually.", "Muted"
            )
        )
        layout.addWidget(plain_label("Available backups", "SectionTitle"))
        self.backup_list = QListWidget()
        for backup in backups:
            item = QListWidgetItem(
                f"{backup.folder_id}  ·  {backup.device.title()}  ·  {backup.created_at[:16]}\n{backup.path.name}"
            )
            item.setData(Qt.ItemDataRole.UserRole, str(backup.path))
            self.backup_list.addItem(item)
        layout.addWidget(self.backup_list, 2)
        target_row = QHBoxLayout()
        target_row.addWidget(plain_label("Restore to:"))
        self.target = QComboBox()
        self.target.addItem("Mac", "mac")
        self.target.addItem("iPad", "ipad")
        target_row.addWidget(self.target)
        self.restore_button = QPushButton("Review restore")
        self.restore_button.setObjectName("DangerButton")
        self.restore_button.setEnabled(False)
        self.backup_list.currentRowChanged.connect(
            lambda row: self.restore_button.setEnabled(row >= 0)
        )
        target_row.addStretch()
        target_row.addWidget(self.restore_button)
        layout.addLayout(target_row)
        layout.addWidget(plain_label("Recent operations", "SectionTitle"))
        operations = QListWidget()
        for event in history:
            operations.addItem(
                f"{event.get('at', '')[:16]}  ·  {event.get('status', '')}  ·  {event.get('farm', '')}"
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
