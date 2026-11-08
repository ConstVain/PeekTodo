"""Translate stored settings into task-mapping options and a source adapter."""

from ..domain.structure import MappingConfig
from ..domain.vocabulary import Vocabulary
from ..sources.base import Source, SourceError
from ..sources.markdown import MarkdownSource
from ..sources.mubu import MubuSource
from ..storage.config import Config


def build_source(cfg: Config) -> Source:
    """按配置造数据源。类型不认识就抛错，由调用方显示成提示。"""
    kind = (cfg.source.get("type") or "").lower()
    if kind == "markdown":
        path = cfg.source_path()
        if path is None:
            raise SourceError("配置里没有填 markdown 路径")
        return MarkdownSource(path, recursive=bool(cfg.source.get("recursive", True)))
    if kind == "mubu":
        doc_id = cfg.source.get("docId")
        if not doc_id:
            raise SourceError("配置里没有填幕布文档 id")
        return MubuSource(doc_id)
    raise SourceError(f"不认识的数据源类型：{kind or '(空)'}")


def build_mapping(cfg: Config) -> MappingConfig:
    raw = cfg.mapping
    return MappingConfig(
        root_path=raw.get("root_path"),
        mode=(raw.get("mode") or "A").upper(),
        aliases=raw.get("aliases") or {},
        vocabulary=Vocabulary.from_config(cfg.vocabulary),
    )
