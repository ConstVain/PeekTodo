"""Refresh tasks, overlay saved checkmarks, and retain the last usable view."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..domain.selection import View, build_view
from ..domain.structure import map_document
from ..sources.base import SourceError
from ..storage.config import Config
from .configuration import build_mapping, build_section_mappings, build_source


@dataclass(frozen=True)
class SectionView:
    title: str
    view: View
from ..storage.state import LocalState


@dataclass(frozen=True)
class Snapshot:
    view: View | None
    level: str
    status: str
    detail: str = ""
    sections: tuple[SectionView, ...] = ()

    @property
    def meta(self) -> dict[str, str]:
        return {"level": self.level, "status": self.status, "detail": self.detail}


class TaskSession:
    def __init__(self, config: Config, state_file: Path):
        self.source = build_source(config)
        self.mapping = build_mapping(config)
        self.section_mappings = build_section_mappings(config, self.mapping)
        self.periods = config.periods
        key = (
            f"mubu:{config.source['docId']}" if self.source.name == "mubu"
            else f"markdown:{config.source_path()}"
        )
        self.state = LocalState(state_file, key)
        self.last_view: View | None = None
        self.last_sections: tuple[SectionView, ...] = ()

    def refresh(self, now: datetime) -> Snapshot:
        try:
            fetch = self.source.fetch()
        except SourceError as exc:
            return Snapshot(
                self.last_view, "error", "读取失败，显示上次数据", str(exc), self.last_sections,
            )

        result = map_document(fetch.tree, self.mapping, today=now.date())
        view = build_view(result, now, self.periods, self.state.is_done)
        sections = []
        issues = list(view.issues)
        for mapping in self.section_mappings:
            mapped = map_document(fetch.tree, mapping, today=now.date())
            section = build_view(mapped, now, self.periods, self.state.is_done)
            title = mapping.root_path[-1]
            sections.append(SectionView(title, section))
            issues.extend(f"{title}：{message}" for message in section.issues)
            if section.unknown:
                issues.append(f"{title}：{len(section.unknown)} 条未识别时间")
        self.last_view = view
        self.last_sections = tuple(sections)
        level = "warn" if (fetch.warnings or view.unknown or issues) else "ok"
        status = f"{fetch.fetched_at:%H:%M} · {fetch.source_name}"
        if fetch.warnings:
            status += " · 数据源警告"
        elif view.unknown:
            status += f" · {len(view.unknown)} 条未识别时间"
        return Snapshot(view, level, status, "\n".join(fetch.warnings + issues), self.last_sections)

    def set_done(self, task_id: str, done: bool) -> None:
        self.state.set_done(task_id, done)

    def remove_section(self, index: int) -> None:
        self.section_mappings = self.section_mappings[:index] + self.section_mappings[index + 1:]
        self.last_sections = self.last_sections[:index] + self.last_sections[index + 1:]
