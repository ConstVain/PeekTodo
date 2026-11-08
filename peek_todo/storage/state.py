"""Persist local checkmarks without editing source documents."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .json_file import write_json

TTL_DAYS = 7


def _timestamp(record: object) -> datetime | None:
    if not isinstance(record, dict) or not isinstance(record.get("done"), bool):
        return None
    try:
        stamp = datetime.fromisoformat(record.get("at", ""))
        return stamp.astimezone().replace(tzinfo=None)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except ValueError as exc:
        raise ValueError(f"Invalid checkmark file: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Invalid checkmark file: {path}")
    return data


def migrate_state(target: Path, legacy_paths: list[Path]) -> None:
    """Copy recent records from old portable files, preferring the newest record."""
    data = _read(target)
    changed = False
    cutoff = datetime.now() - timedelta(days=TTL_DAYS)
    for path in dict.fromkeys(path.resolve() for path in legacy_paths):
        if path == target.resolve():
            continue
        try:
            legacy = _read(path)
        except (OSError, ValueError):
            continue
        for key, records in legacy.items():
            if not isinstance(records, dict):
                continue
            bucket = data.get(key)
            if not isinstance(bucket, dict):
                bucket = {}
            for task_id, record in records.items():
                # Old Markdown IDs only contain line numbers and can point at another task.
                if key.startswith("markdown:") and not task_id.startswith("md2:"):
                    continue
                stamp = _timestamp(record)
                current = _timestamp(bucket.get(task_id))
                if stamp and stamp >= cutoff and (current is None or stamp > current):
                    bucket[task_id] = record
                    data[key] = bucket
                    changed = True
    if changed:
        write_json(target, data)


class LocalState:
    def __init__(self, path: str | Path, source_key: str, ttl_days: int = TTL_DAYS):
        self.path = Path(path)
        self.source_key = source_key
        self.ttl_days = ttl_days
        self._data = _read(self.path)

    def _bucket(self, data: dict) -> dict:
        bucket = data.get(self.source_key)
        return bucket if isinstance(bucket, dict) else {}

    def is_done(self, task_id: str, fallback: bool) -> bool:
        record = self._bucket(self._data).get(task_id)
        stamp = _timestamp(record)
        if stamp is None or datetime.now() - stamp > timedelta(days=self.ttl_days):
            return fallback
        return record["done"]

    def set_done(self, task_id: str, done: bool) -> None:
        data = _read(self.path)
        bucket = self._bucket(data)
        bucket[task_id] = {"done": done, "at": datetime.now().isoformat()}
        cutoff = datetime.now() - timedelta(days=self.ttl_days)
        data[self.source_key] = {
            key: value for key, value in bucket.items()
            if (stamp := _timestamp(value)) is not None and stamp >= cutoff
        }
        write_json(self.path, data)
        self._data = data

    def clear(self) -> None:
        data = _read(self.path)
        data.pop(self.source_key, None)
        write_json(self.path, data)
        self._data = data

    def count(self) -> int:
        return len(self._bucket(self._data))
