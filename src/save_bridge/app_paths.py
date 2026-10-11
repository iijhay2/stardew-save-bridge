from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @classmethod
    def default(cls) -> "AppPaths":
        return cls(user_data_path("Stardew Save Bridge", appauthor=False))

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def staging(self) -> Path:
        return self.root / "staging"

    @property
    def history(self) -> Path:
        return self.root / "history.jsonl"

    def ensure(self) -> None:
        for path in (self.root, self.backups, self.staging):
            path.mkdir(parents=True, exist_ok=True)
