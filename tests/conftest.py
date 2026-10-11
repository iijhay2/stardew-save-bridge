import os
from contextlib import contextmanager
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def make_farm(root: Path, folder_id: str, farm_name: str, money: int, day: int = 5) -> Path:
    folder = root / folder_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SaveGameInfo").write_text(
        f"<Farmer><name>Robin</name><farmName>{farm_name}</farmName>"
        f"<money>{money}</money><gameVersion>1.6.15</gameVersion></Farmer>",
        encoding="utf-8",
    )
    (folder / folder_id).write_text(
        f"<SaveGame><player><name>Robin</name><farmName>{farm_name}</farmName>"
        f"<money>{money}</money></player><dayOfMonth>{day}</dayOfMonth>"
        "<currentSeason>spring</currentSeason><year>2</year>"
        "<gameVersion>1.6.15</gameVersion></SaveGame>",
        encoding="utf-8",
    )
    return folder


class FakeUSB:
    def __init__(self, root: Path) -> None:
        self.root = root

    @contextmanager
    def mounted_documents(self):
        yield self.root, "Test iPad", "test.stardew"

    def replace_verified(self, folder_id, staged_source, expected, operation_id, old_manifest):
        from save_bridge.services.bridge import replace_verified

        replace_verified(self.root / folder_id, staged_source, expected, operation_id)


@pytest.fixture
def farm_factory():
    return make_farm
