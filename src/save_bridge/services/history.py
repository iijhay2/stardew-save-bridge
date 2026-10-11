import json
import os
from datetime import UTC, datetime
from pathlib import Path

from save_bridge.errors import BridgeError


class HistoryService:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, operation_id: str, status: str, **details: object) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "operation_id": operation_id,
            "at": datetime.now(UTC).isoformat(),
            "status": status,
            **details,
        }
        payload = (json.dumps(record, sort_keys=True, default=str) + "\n").encode()
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise BridgeError(f"Could not write operation history: {exc}") from exc

    def recent(self, limit: int = 100) -> list[dict]:
        if not self.path.exists():
            return []
        latest: dict[str, dict] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                latest[str(record["operation_id"])] = record
            except (ValueError, KeyError):
                continue
        return list(reversed(list(latest.values())[-limit:]))
