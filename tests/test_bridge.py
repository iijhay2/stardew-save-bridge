import os
import plistlib
from contextlib import contextmanager
from pathlib import Path

import pytest
from conftest import FakeUSB

from save_bridge.app_paths import AppPaths
from save_bridge.errors import BridgeError, ChangedSaveError
from save_bridge.services.backup import BackupService
from save_bridge.services.bridge import BridgeService, replace_verified
from save_bridge.services.ipad import USBBridge, resolve_tool
from save_bridge.services.save_scan import manifest_for, scan_root


def make_service(tmp_path: Path) -> BridgeService:
    mac = tmp_path / "mac"
    ipad = tmp_path / "ipad"
    mac.mkdir()
    ipad.mkdir()
    return BridgeService(AppPaths(tmp_path / "app"), mac, FakeUSB(ipad))


def test_multiple_farms_show_name_player_money_and_date(tmp_path, farm_factory):
    root = tmp_path / "mac"
    farm_factory(root, "Bluebell_123", "Bluebell", 123456)
    farm_factory(root, "Moss_456", "Moss", 42)
    saves = scan_root(root, "mac")
    assert [s.farm_name for s in saves] == ["Bluebell", "Moss"]
    assert [s.money for s in saves] == [123456, 42]
    assert saves[0].player_name == "Robin"
    assert saves[0].in_game_date == "Spring 5, Year 2"
    assert all(s.valid for s in saves)


def test_backup_round_trip_and_reject_corruption(tmp_path, farm_factory):
    root = tmp_path / "mac"
    farm_factory(root, "Bluebell_123", "Bluebell", 123456)
    save = scan_root(root, "mac")[0]
    backups = BackupService(tmp_path / "backups")
    archive = backups.create(save, "op1")
    assert backups.verify(archive.path).manifest == save.manifest
    assert backups.verify(archive.path).farm_name == "Bluebell"
    extracted = tmp_path / "extracted"
    backups.extract(archive, extracted)
    assert manifest_for(extracted) == save.manifest
    archive.path.write_bytes(b"broken")
    with pytest.raises(BridgeError):
        backups.verify(archive.path)


def test_malformed_save_is_visible_but_not_transferable(tmp_path, farm_factory):
    root = tmp_path / "mac"
    folder = farm_factory(root, "Bluebell_123", "Bluebell", 123456)
    (folder / "Bluebell_123").write_text("<SaveGame><broken>")
    save = scan_root(root, "mac")[0]
    assert not save.valid
    assert any("malformed" in warning for warning in save.warnings)


def test_two_way_transfer_and_restore_with_verified_backups(tmp_path, farm_factory, monkeypatch):
    monkeypatch.setattr("save_bridge.services.bridge.ensure_game_closed", lambda: None)
    service = make_service(tmp_path)
    farm_factory(service.mac_root, "Bluebell_123", "Bluebell", 123456)
    farm_factory(service.usb.root, "Bluebell_123", "Bluebell", 45)
    before = service.scan()
    source = before.mac_saves[0]
    old_ipad = before.ipad_saves[0]
    prepared = service.prepare(source, old_ipad)
    assert prepared.source_backup.path.exists()
    assert prepared.destination_backup and prepared.destination_backup.path.exists()
    service.execute(prepared)
    after = service.scan()
    assert after.ipad_saves[0].money == 123456
    assert after.ipad_saves[0].manifest == after.mac_saves[0].manifest
    restore = service.prepare_restore(prepared.destination_backup.path, "ipad")
    service.execute_restore(restore)
    assert service.scan().ipad_saves[0].money == 45
    reverse = service.scan()
    prepared_reverse = service.prepare(reverse.ipad_saves[0], reverse.mac_saves[0])
    service.execute(prepared_reverse)
    assert service.scan().mac_saves[0].money == 45


def test_changed_destination_blocks_write_and_keeps_backups(tmp_path, farm_factory, monkeypatch):
    monkeypatch.setattr("save_bridge.services.bridge.ensure_game_closed", lambda: None)
    service = make_service(tmp_path)
    farm_factory(service.mac_root, "Bluebell_123", "Bluebell", 123456)
    farm_factory(service.usb.root, "Bluebell_123", "Bluebell", 45)
    before = service.scan()
    prepared = service.prepare(before.mac_saves[0], before.ipad_saves[0])
    (service.usb.root / "Bluebell_123" / "SaveGameInfo").write_text(
        "<Farmer><money>777</money></Farmer>"
    )
    with pytest.raises(ChangedSaveError):
        service.execute(prepared)
    assert "777" in (service.usb.root / "Bluebell_123" / "SaveGameInfo").read_text()
    assert prepared.destination_backup and prepared.destination_backup.path.exists()


def test_replacement_failure_restores_previous_folder(tmp_path, farm_factory, monkeypatch):
    old = farm_factory(tmp_path / "target", "Bluebell_123", "Bluebell", 45)
    incoming = farm_factory(tmp_path / "source", "Bluebell_123", "Bluebell", 123456)
    expected = manifest_for(incoming)
    original_replace = os.replace
    attempts = 0

    def fail_second_replace(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("simulated write interruption")
        return original_replace(source, destination)

    monkeypatch.setattr("save_bridge.services.bridge.os.replace", fail_second_replace)
    with pytest.raises(BridgeError):
        replace_verified(old, incoming, expected, "op1")
    assert scan_root(old.parent, "ipad")[0].money == 45


def test_cancelled_prepare_never_changes_destination(tmp_path, farm_factory, monkeypatch):
    monkeypatch.setattr("save_bridge.services.bridge.ensure_game_closed", lambda: None)
    service = make_service(tmp_path)
    farm_factory(service.mac_root, "Bluebell_123", "Bluebell", 123456)
    farm_factory(service.usb.root, "Bluebell_123", "Bluebell", 45)
    before = service.scan()
    with pytest.raises(BridgeError, match="cancelled"):
        service.prepare(before.mac_saves[0], before.ipad_saves[0], cancelled=lambda: True)
    assert service.scan().ipad_saves[0].money == 45


def test_new_farm_copy_has_source_backup_and_records_empty_target(
    tmp_path, farm_factory, monkeypatch
):
    monkeypatch.setattr("save_bridge.services.bridge.ensure_game_closed", lambda: None)
    service = make_service(tmp_path)
    farm_factory(service.mac_root, "Bluebell_123", "Bluebell", 123456)
    source = service.scan().mac_saves[0]
    prepared = service.prepare(source, None)
    assert prepared.destination_backup is None
    service.execute(prepared)
    assert service.scan().ipad_saves[0].money == 123456
    assert service.history.recent()[0]["status"] == "succeeded"


def test_existing_nonfarm_target_is_never_replaced(tmp_path, farm_factory, monkeypatch):
    monkeypatch.setattr("save_bridge.services.bridge.ensure_game_closed", lambda: None)
    service = make_service(tmp_path)
    farm_factory(service.mac_root, "Bluebell_123", "Bluebell", 123456)
    collision = service.usb.root / "Bluebell_123"
    collision.write_text("important unrelated file")
    source = service.scan().mac_saves[0]
    with pytest.raises(BridgeError, match="destination path exists"):
        service.prepare(source, None)
    assert collision.read_text() == "important unrelated file"


def test_mac_restore_works_without_connected_ipad(tmp_path, farm_factory, monkeypatch):
    monkeypatch.setattr("save_bridge.services.bridge.ensure_game_closed", lambda: None)
    service = make_service(tmp_path)
    farm = farm_factory(service.mac_root, "Bluebell_123", "Bluebell", 123456)
    original = scan_root(service.mac_root, "mac")[0]
    archive = service.backups.create(original, "initial")
    (farm / "SaveGameInfo").write_text(
        "<Farmer><name>Robin</name><farmName>Bluebell</farmName>"
        "<money>45</money></Farmer>"
    )

    class DisconnectedUSB:
        @contextmanager
        def mounted_documents(self):
            raise AssertionError("Mac restore must not connect to the iPad")
            yield

    service.usb = DisconnectedUSB()
    prepared = service.prepare_restore(archive.path, "mac")
    assert prepared.destination_backup is not None
    service.execute_restore(prepared)
    assert scan_root(service.mac_root, "mac")[0].money == 123456


def test_stardew_app_discovery_requires_file_sharing(tmp_path, monkeypatch):
    apps = [
        {"CFBundleIdentifier": "com.example.notes", "UIFileSharingEnabled": True},
        {
            "CFBundleIdentifier": "com.chucklefish.stardewvalley",
            "CFBundleDisplayName": "Stardew Valley",
            "UIFileSharingEnabled": True,
        },
    ]
    monkeypatch.setattr("save_bridge.services.ipad.resolve_tool", lambda _name: "tool")
    monkeypatch.setattr(
        USBBridge, "_run", staticmethod(lambda _cmd, timeout=30: plistlib.dumps(apps).decode())
    )
    assert USBBridge(tmp_path).stardew_app_id("device") == "com.chucklefish.stardewvalley"


def test_finder_launch_can_resolve_usb_tools_outside_path(tmp_path, monkeypatch):
    tool = tmp_path / "afcclient"
    tool.write_text("#!/bin/sh\nexit 0\n")
    tool.chmod(0o755)
    monkeypatch.setattr("save_bridge.services.ipad.shutil.which", lambda _name: None)
    monkeypatch.setattr("save_bridge.services.ipad.TOOL_DIRECTORIES", (tmp_path,))
    assert resolve_tool("afcclient") == str(tool)
