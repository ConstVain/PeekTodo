"""本地勾选状态。

约束：**绝不修改源文件**（Markdown / 幕布都不碰）。勾选只写在这个 JSON 里，
按「源标识 + 任务 id」保存，超过 TTL 自动丢弃，避免陈年旧勾盖住真实状态。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

TTL_DAYS = 7


class LocalState:
    def __init__(self, path: str | Path, source_key: str, ttl_days: int = TTL_DAYS):
        self.path = Path(path)
        self.source_key = source_key
        self.ttl_days = ttl_days
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._data = raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            self._data = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            pass

    def _bucket(self) -> dict:
        return self._data.setdefault(self.source_key, {})

    def is_done(self, task_id: str, fallback: bool) -> bool:
        """源里的状态是底，本地勾选覆盖它。"""
        record = self._bucket().get(task_id)
        if not record:
            return fallback
        try:
            stamp = datetime.fromisoformat(record.get("at", ""))
        except ValueError:
            return fallback
        if datetime.now() - stamp > timedelta(days=self.ttl_days):
            self._bucket().pop(task_id, None)
            self._save()
            return fallback
        return bool(record.get("done"))

    def set_done(self, task_id: str, done: bool) -> None:
        self._bucket()[task_id] = {
            "done": bool(done),
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        self._save()

    def clear(self) -> None:
        self._data.pop(self.source_key, None)
        self._save()

    def count(self) -> int:
        return len(self._bucket())
