import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from save_bridge.models import FarmSave, ScanResult
from save_bridge.services.backup import BackupInfo
from save_bridge.services.bridge import BridgeService, PreparedRestore, PreparedTransfer
from save_bridge.ui.components import (
    IPAD_MONEY_ROLE,
    MAC_MONEY_ROLE,
    CopyCard,
    FarmItemDelegate,
    flower_pixmap,
    money_text,
    plain_label,
)
from save_bridge.ui.dialogs import ConfirmationDialog, HistoryDialog, ProgressDialog


class Job(QObject):
    progress = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable, cancellable: bool = False) -> None:
        super().__init__()
        self.fn = fn
        self.cancel_event = threading.Event()
        self.cancellable = cancellable

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(self.progress.emit, self.cancel_event.is_set)
            self.succeeded.emit(result)
        except Exception as exc:  # noqa: BLE001 - all worker failures must reach the UI
            self.failed.emit(str(exc))


@dataclass
class JobRun:
    thread: QThread
    job: Job
    dialog: ProgressDialog | None
    success: Callable[[object], None]
    result: object | None = None
    error: str | None = None


class BridgeWindow(QMainWindow):
    def __init__(self, service: BridgeService | None = None) -> None:
        super().__init__()
        self.service = service or BridgeService()
        self.scan_result = ScanResult((), (), "Scanning…")
        self.selected_folder: str | None = None
        self._jobs: list[JobRun] = []
        self._busy = False
        self.setWindowTitle("Stardew Save Bridge — Farm Journal")
        self.setMinimumSize(940, 650)
        self.resize(1150, 760)
        self._build_ui()
        self._build_menus()
        QTimer.singleShot(0, self.refresh)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(26, 24, 26, 22)
        outer.setSpacing(17)

        hero = QFrame()
        hero.setObjectName("Hero")
        hero_row = QHBoxLayout(hero)
        hero_row.setContentsMargins(21, 16, 21, 16)
        icon = QLabel()
        icon.setPixmap(flower_pixmap())
        hero_row.addWidget(icon)
        brand = QVBoxLayout()
        brand.setSpacing(1)
        brand.addWidget(plain_label("YOUR FARM, SAFELY ON BOTH DEVICES", "Eyebrow"))
        brand.addWidget(plain_label("Farm Journal", "AppTitle"))
        hero_row.addLayout(brand)
        hero_row.addStretch()
        self.connection = plain_label("Scanning iPad…", "StatusWarn")
        hero_row.addWidget(self.connection)
        outer.addWidget(hero)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        outer.addWidget(split, 1)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 20, 16, 16)
        side.setSpacing(11)
        side.addWidget(plain_label("YOUR SAVES", "Eyebrow"))
        side.addWidget(plain_label("Choose a farm", "SectionTitle"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search farms or farmers")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._populate_farms)
        side.addWidget(self.search)
        self.farms = QListWidget()
        self.farms.setItemDelegate(FarmItemDelegate(self.farms))
        self.farms.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.farms.setAccessibleName("Farms on Mac and iPad")
        self.farms.currentItemChanged.connect(self._farm_selected)
        side.addWidget(self.farms, 1)
        self.list_hint = plain_label("Select the exact save you want to copy.", "Muted")
        side.addWidget(self.list_hint)
        split.addWidget(sidebar)

        workspace = QFrame()
        workspace.setObjectName("Workspace")
        work = QVBoxLayout(workspace)
        work.setContentsMargins(24, 22, 24, 20)
        work.setSpacing(14)
        top = QHBoxLayout()
        title_stack = QVBoxLayout()
        title_stack.setSpacing(4)
        title_stack.addWidget(plain_label("FARM COMPARISON", "Eyebrow"))
        self.farm_title = plain_label("Pick a farm to begin", "PageTitle")
        title_stack.addWidget(self.farm_title)
        top.addLayout(title_stack)
        top.addStretch()
        self.refresh_button = QPushButton("Refresh saves")
        self.refresh_button.clicked.connect(self.refresh)
        top.addWidget(self.refresh_button)
        work.addLayout(top)
        self.summary = plain_label(
            "Your Mac farms appear here. Connect an unlocked iPad to compare copies.", "Muted"
        )
        work.addWidget(self.summary)
        banner_row = QHBoxLayout()
        self.banner = plain_label("", "Warning")
        self.banner.hide()
        banner_row.addWidget(self.banner, 1)
        self.setup_button = QPushButton("iPad setup")
        self.setup_button.clicked.connect(self.show_setup)
        self.setup_button.hide()
        banner_row.addWidget(self.setup_button)
        work.addLayout(banner_row)

        self.empty_card = QFrame()
        self.empty_card.setObjectName("EmptyCard")
        empty = QVBoxLayout(self.empty_card)
        empty.setContentsMargins(38, 40, 38, 40)
        empty.setSpacing(12)
        empty.addStretch()
        empty_icon = QLabel()
        empty_icon.setPixmap(flower_pixmap().scaled(64, 64))
        empty.addWidget(empty_icon, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.empty_title = plain_label("Choose a farm", "FarmTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(self.empty_title)
        self.empty_text = plain_label(
            "Pick a save from the journal to compare Mac and iPad copies.", "Muted"
        )
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(self.empty_text)
        empty.addStretch()
        work.addWidget(self.empty_card, 1)

        self.copies_widget = QWidget()
        copies = QHBoxLayout(self.copies_widget)
        copies.setContentsMargins(0, 0, 0, 0)
        copies.setSpacing(13)
        self.mac_card = CopyCard("mac")
        self.ipad_card = CopyCard("ipad")
        copies.addWidget(self.mac_card, 1)
        copies.addWidget(self.ipad_card, 1)
        work.addWidget(self.copies_widget, 1)
        self.group = QButtonGroup(self)
        self.group.addButton(self.mac_card.radio)
        self.group.addButton(self.ipad_card.radio)
        self.mac_card.radio.toggled.connect(self._update_actions)
        self.ipad_card.radio.toggled.connect(self._update_actions)

        actions = QHBoxLayout()
        self.history_button = QPushButton("Backups & history")
        self.history_button.clicked.connect(self.show_history)
        actions.addWidget(self.history_button)
        actions.addStretch()
        self.prepare_button = QPushButton("Choose a source copy")
        self.prepare_button.setObjectName("Primary")
        self.prepare_button.setEnabled(False)
        self.prepare_button.setShortcut(QKeySequence("Meta+Return"))
        self.prepare_button.clicked.connect(self.prepare_transfer)
        actions.addWidget(self.prepare_button)
        work.addLayout(actions)
        split.addWidget(workspace)
        split.setSizes([315, 800])
        self.statusBar().showMessage("Ready")
        self._show_selected()

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        refresh = QAction("Refresh Saves", self)
        refresh.setShortcut(QKeySequence("Meta+R"))
        refresh.triggered.connect(self.refresh)
        file_menu.addAction(refresh)
        history = QAction("Backups & History", self)
        history.setShortcut(QKeySequence("Meta+Shift+B"))
        history.triggered.connect(self.show_history)
        file_menu.addAction(history)
        help_menu = self.menuBar().addMenu("Help")
        setup = QAction("iPad Setup", self)
        setup.triggered.connect(self.show_setup)
        help_menu.addAction(setup)

    def _run_job(
        self,
        title: str,
        fn: Callable,
        success: Callable[[object], None],
        *,
        show_progress: bool = True,
        cancellable: bool = False,
    ) -> None:
        if self._busy:
            return
        self._busy = True
        self.refresh_button.setEnabled(False)
        self.prepare_button.setEnabled(False)
        dialog = ProgressDialog(title, cancellable, self) if show_progress else None
        thread = QThread(self)
        job = Job(fn, cancellable)
        job.moveToThread(thread)
        thread.started.connect(job.run)
        if dialog:
            job.progress.connect(dialog.set_step)
            dialog.cancel_button.clicked.connect(job.cancel_event.set)
            dialog.cancel_button.clicked.connect(dialog.request_cancel)
            dialog.open()

        self._jobs.append(JobRun(thread, job, dialog, success))
        job.succeeded.connect(self._job_succeeded)
        job.failed.connect(self._job_failed)
        thread.finished.connect(job.deleteLater)
        thread.finished.connect(self._job_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _run_for_sender(self, sender: QObject) -> JobRun | None:
        return next((run for run in self._jobs if run.job == sender or run.thread == sender), None)

    @Slot(object)
    def _job_succeeded(self, result: object) -> None:
        run = self._run_for_sender(self.sender())
        if run:
            run.result = result
            run.thread.quit()

    @Slot(str)
    def _job_failed(self, message: str) -> None:
        run = self._run_for_sender(self.sender())
        if run:
            run.error = message
            run.thread.quit()

    @Slot()
    def _job_finished(self) -> None:
        run = self._run_for_sender(self.sender())
        if run is None:
            return
        self._jobs.remove(run)
        self._busy = False
        self.refresh_button.setEnabled(True)
        self._update_actions()
        if run.dialog:
            run.dialog.done(1)
        if run.error is not None:
            if "cancel" in run.error.lower():
                self.statusBar().showMessage(
                    "Preparation cancelled. Existing farms were not changed.", 8000
                )
            else:
                QMessageBox.critical(self, "Operation stopped", run.error)
                self.statusBar().showMessage(run.error, 10000)
        else:
            run.success(run.result)

    def refresh(self) -> None:
        self.connection.setText("Scanning iPad…")
        self.statusBar().showMessage("Scanning farm folders…")
        self._run_job(
            "Scanning your farms",
            lambda _p, _c: self.service.scan(),
            self._scan_done,
            show_progress=False,
        )

    def _scan_done(self, result: object) -> None:
        assert isinstance(result, ScanResult)
        self.scan_result = result
        connected = result.ipad_status == "Connected and ready"
        self.connection.setObjectName("StatusGood" if connected else "StatusWarn")
        self.connection.setText(
            f"{result.ipad_device_name} connected" if connected else "iPad needs setup"
        )
        self.connection.style().unpolish(self.connection)
        self.connection.style().polish(self.connection)
        self._populate_farms()
        self.statusBar().showMessage("Scan complete" if connected else result.ipad_status, 10000)

    def _all_ids(self) -> list[str]:
        saves = {
            s.folder_id: s for s in (*self.scan_result.ipad_saves, *self.scan_result.mac_saves)
        }
        return sorted(saves, key=lambda folder: (saves[folder].farm_name.casefold(), folder))

    def _save(self, device: str, folder_id: str | None) -> FarmSave | None:
        if folder_id is None:
            return None
        source = self.scan_result.mac_saves if device == "mac" else self.scan_result.ipad_saves
        return next((save for save in source if save.folder_id == folder_id), None)

    def _populate_farms(self) -> None:
        selected = self.selected_folder
        search = self.search.text().casefold().strip()
        self.farms.blockSignals(True)
        self.farms.clear()
        for folder_id in self._all_ids():
            mac = self._save("mac", folder_id)
            ipad = self._save("ipad", folder_id)
            save = mac or ipad
            assert save is not None
            haystack = f"{folder_id} {save.farm_name} {save.player_name or ''}".casefold()
            if search and search not in haystack:
                continue
            mac_money = money_text(mac.money) if mac else "—"
            ipad_money = money_text(ipad.money) if ipad else "—"
            item = QListWidgetItem(f"{save.farm_name} Farm")
            item.setData(Qt.ItemDataRole.UserRole, folder_id)
            item.setData(MAC_MONEY_ROLE, mac_money)
            item.setData(IPAD_MONEY_ROLE, ipad_money)
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                f"{save.farm_name} Farm, Mac {mac_money}, iPad {ipad_money}",
            )
            item.setSizeHint(QSize(0, 88))
            item.setToolTip(f"{folder_id}\nPlayer: {save.player_name or 'Unavailable'}")
            self.farms.addItem(item)
            if folder_id == selected:
                self.farms.setCurrentItem(item)
        self.farms.blockSignals(False)
        if selected and not any(
            self.farms.item(i).data(Qt.ItemDataRole.UserRole) == selected
            for i in range(self.farms.count())
        ):
            self.selected_folder = None
        self.list_hint.setText(
            f"{self.farms.count()} farm save{'s' if self.farms.count() != 1 else ''} found"
            if self.farms.count()
            else "No farms found. Start a farm in Stardew, then refresh."
        )
        self._show_selected()

    def _farm_selected(
        self, item: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        self.selected_folder = item.data(Qt.ItemDataRole.UserRole) if item else None
        self._show_selected()

    def _show_selected(self) -> None:
        self.group.setExclusive(False)
        self.mac_card.radio.setChecked(False)
        self.ipad_card.radio.setChecked(False)
        self.group.setExclusive(True)
        mac = self._save("mac", self.selected_folder)
        ipad = self._save("ipad", self.selected_folder)
        self.mac_card.update_save(mac)
        self.ipad_card.update_save(ipad)
        if self.selected_folder and self.scan_result.ipad_status not in (
            "Connected and ready",
            "Scanning…",
        ):
            self.ipad_card.show_unavailable(self.scan_result.ipad_status)
        self.mac_card.set_active(False)
        self.ipad_card.set_active(False)
        if self.selected_folder:
            save = mac or ipad
            assert save is not None
            self.farm_title.setText(f"{save.farm_name} Farm")
            if mac and ipad and mac.manifest and ipad.manifest:
                self.summary.setText(
                    "Both copies have identical files."
                    if mac.manifest == ipad.manifest
                    else "The copies differ. Choose the one you want to keep."
                )
            else:
                self.summary.setText(
                    "Select the copy to use. The other device will receive this farm."
                )
        else:
            self.farm_title.setText("Pick a farm to begin")
            self.summary.setText(
                "Your Mac farms appear here. Connect an unlocked iPad to compare copies."
            )
        blocked = self.scan_result.ipad_status not in ("Connected and ready", "Scanning…")
        self.banner.setText(self.scan_result.ipad_status if blocked else "")
        self.banner.setVisible(blocked)
        self.setup_button.setVisible(blocked)
        self.copies_widget.setVisible(self.selected_folder is not None)
        self.empty_card.setVisible(self.selected_folder is None)
        if self.selected_folder is None:
            if self._all_ids():
                self.empty_title.setText("Choose a farm")
                self.empty_text.setText(
                    "Pick a save from the journal to compare Mac and iPad copies."
                )
            else:
                self.empty_title.setText("No farms found yet")
                self.empty_text.setText(
                    "Save a farm in Stardew Valley on your Mac, then choose Refresh Saves."
                )
        self._update_actions()

    def _update_actions(self) -> None:
        mac = self.mac_card.radio.isChecked()
        ipad = self.ipad_card.radio.isChecked()
        self.mac_card.set_active(mac)
        self.ipad_card.set_active(ipad)
        ready = self.scan_result.ipad_status == "Connected and ready"
        enabled = bool(self.selected_folder and (mac or ipad) and ready and not self._busy)
        self.prepare_button.setEnabled(enabled)
        if mac:
            self.prepare_button.setText("Prepare Mac → iPad")
        elif ipad:
            self.prepare_button.setText("Prepare iPad → Mac")
        else:
            self.prepare_button.setText("Choose a source copy")
        self.prepare_button.setToolTip("" if ready else self.scan_result.ipad_status)

    def prepare_transfer(self) -> None:
        source = self.mac_card.save if self.mac_card.radio.isChecked() else self.ipad_card.save
        if source is None or not source.valid:
            return
        destination = self.ipad_card.save if source.device == "mac" else self.mac_card.save
        self._run_job(
            "Preparing safe transfer",
            lambda progress, cancelled: self.service.prepare(
                source, destination, progress, cancelled
            ),
            self._transfer_prepared,
            cancellable=True,
        )

    def _transfer_prepared(self, result: object) -> None:
        assert isinstance(result, PreparedTransfer)
        confirmation = ConfirmationDialog(result, self)
        if confirmation.exec():
            self._run_job(
                "Transferring farm",
                lambda progress, _cancelled: self.service.execute(result, progress),
                lambda _value: self._operation_done(
                    f"{result.source.farm_name} Farm was copied and verified on {result.target_device.title()}.",
                    result.target_device,
                ),
            )
        else:
            self.service.cancel(result)
            self.statusBar().showMessage("Transfer cancelled. Verified backups were kept.", 8000)

    def _operation_done(self, message: str, target_device: str) -> None:
        next_step = (
            "Eject the iPad safely, then check the farm in Stardew's Load Game screen."
            if target_device == "ipad"
            else "Check the farm in Stardew's Load Game screen on your Mac."
        )
        QMessageBox.information(
            self,
            "Farm ready",
            f"{message}\n\n{next_step}",
        )
        self.refresh()

    def show_history(self) -> None:
        if self._busy:
            return
        self._run_job(
            "Checking saved backups",
            lambda _progress, _cancelled: (
                self.service.available_backups(),
                self.service.history.recent(),
            ),
            self._history_loaded,
        )

    def _history_loaded(self, result: object) -> None:
        backups, history = cast(tuple[list[BackupInfo], list[dict]], result)
        dialog = HistoryDialog(backups, history, self)

        def restore() -> None:
            selected = dialog.selected_restore()
            if selected is None:
                return
            dialog.accept()
            archive, target = selected
            self._run_job(
                "Preparing safe restore",
                lambda progress, _cancelled: self.service.prepare_restore(
                    archive, target, progress
                ),
                self._restore_prepared,
            )

        dialog.restore_button.clicked.connect(restore)
        dialog.exec()

    def _restore_prepared(self, result: object) -> None:
        assert isinstance(result, PreparedRestore)
        confirmation = ConfirmationDialog(result, self)
        if confirmation.exec():
            self._run_job(
                "Restoring farm",
                lambda progress, _cancelled: self.service.execute_restore(result, progress),
                lambda _value: self._operation_done(
                    f"{result.archive.folder_id} was restored and verified on {result.target_device.title()}.",
                    result.target_device,
                ),
            )
        else:
            self.service.cancel_restore(result)

    def show_setup(self) -> None:
        QMessageBox.information(
            self,
            "Connect your iPad",
            "1. Close Stardew Valley on both devices.\n"
            "2. Connect and unlock your iPad with a USB cable.\n"
            "3. Tap Trust This Computer if asked.\n"
            "4. Install libimobiledevice and ideviceinstaller, then click Refresh Saves.\n\n"
            "The app only opens Stardew Valley's File Sharing Documents folder.",
        )

    def closeEvent(self, event) -> None:
        if self._busy:
            QMessageBox.information(
                self,
                "Operation in progress",
                "Wait for the current scan or transfer to finish before closing.",
            )
            event.ignore()
        else:
            event.accept()
