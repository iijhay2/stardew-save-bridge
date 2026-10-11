from conftest import FakeUSB
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from save_bridge.app_paths import AppPaths
from save_bridge.errors import DeviceUnavailableError
from save_bridge.services.bridge import BridgeService
from save_bridge.ui.dialogs import ConfirmationDialog
from save_bridge.ui.window import BridgeWindow


class StaticBridgeWindow(BridgeWindow):
    def refresh(self) -> None:
        pass


def test_farm_journal_requires_selection_and_shows_money(tmp_path, farm_factory, qtbot):
    mac = tmp_path / "mac"
    ipad = tmp_path / "ipad"
    mac.mkdir()
    ipad.mkdir()
    farm_factory(mac, "Bluebell_123", "Bluebell", 123456)
    farm_factory(mac, "Moss_456", "Moss", 42)
    farm_factory(ipad, "Bluebell_123", "Bluebell", 888)
    service = BridgeService(AppPaths(tmp_path / "app"), mac, FakeUSB(ipad))
    window = StaticBridgeWindow(service)
    qtbot.addWidget(window)
    window.show()
    window._scan_done(service.scan())
    assert window.selected_folder is None
    assert not window.prepare_button.isEnabled()
    window.farms.setCurrentRow(0)
    assert window.farm_title.text() == "Bluebell Farm"
    assert window.mac_card.money_label.text() == "123,456g"
    assert window.ipad_card.money_label.text() == "888g"
    qtbot.mouseClick(window.mac_card.radio, Qt.MouseButton.LeftButton)
    assert window.prepare_button.isEnabled()
    assert window.prepare_button.text() == "Prepare Mac → iPad"


def test_unscanned_ipad_is_not_mislabeled_as_empty(tmp_path, farm_factory, qtbot):
    mac = tmp_path / "mac"
    mac.mkdir()
    farm_factory(mac, "Bluebell_123", "Bluebell", 123456)

    class DisconnectedUSB:
        def mounted_documents(self):
            raise DeviceUnavailableError("Connect and unlock the iPad")

    service = BridgeService(AppPaths(tmp_path / "app"), mac, DisconnectedUSB())
    window = StaticBridgeWindow(service)
    qtbot.addWidget(window)
    window._scan_done(service.scan())
    window.farms.setCurrentRow(0)
    assert window.ipad_card.farm_label.text() == "iPad copy unavailable"
    assert not window.prepare_button.isEnabled()


def test_confirmation_names_target_and_requires_acknowledgement(
    tmp_path, farm_factory, qtbot, monkeypatch
):
    monkeypatch.setattr("save_bridge.services.bridge.ensure_game_closed", lambda: None)
    mac = tmp_path / "mac"
    ipad = tmp_path / "ipad"
    mac.mkdir()
    ipad.mkdir()
    farm_factory(mac, "Bluebell_123", "Bluebell", 123456)
    farm_factory(ipad, "Bluebell_123", "Bluebell", 45)
    service = BridgeService(AppPaths(tmp_path / "app"), mac, FakeUSB(ipad))
    scan = service.scan()
    prepared = service.prepare(scan.mac_saves[0], scan.ipad_saves[0])
    dialog = ConfirmationDialog(prepared)
    qtbot.addWidget(dialog)
    assert not dialog.confirm.isEnabled()
    assert prepared.target_location in "\n".join(
        label.text() for label in dialog.findChildren(QLabel)
    )
    dialog.acknowledge.setChecked(True)
    assert dialog.confirm.isEnabled()
    service.cancel(prepared)
