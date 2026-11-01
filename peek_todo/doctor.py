"""命令行体检：不打开窗口，直接看程序把文档读成了什么。

    python -m peek_todo.doctor                         # 用当前目录的 config.json
    python -m peek_todo.doctor --config 路径
    python -m peek_todo.doctor --source md --path notes.md --root 规划 --mode A
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config, build_mapping, build_source
from .report import build_report, render_report
from .sources.base import SourceError
from .structure import map_document


def _config_from_args(args) -> Config:
    if args.source:
        raw = {
            "source": {"type": args.source, "path": args.path, "docId": args.doc_id},
            "mapping": {
                "root_path": args.root.split(">") if args.root else None,
                "mode": args.mode or "week",
            },
        }
        return Config(path=Path("config.json").resolve(), raw=raw)
    return Config.load(args.config)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="peek_todo.doctor", description="检查文档能不能被正确解析")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--source", choices=["markdown", "mubu"], help="临时指定数据源，忽略配置")
    parser.add_argument("--path", help="markdown 文件或文件夹")
    parser.add_argument("--doc-id", dest="doc_id", help="幕布文档 id")
    parser.add_argument("--root", help="根节点标题路径，多级用 > 分隔")
    parser.add_argument("--mode", choices=["week", "due", "A", "B", "a", "b"], help="结构模式：week=周计划，due=截止日")
    parser.add_argument("--json", action="store_true", help="输出机器可读的 JSON")
    args = parser.parse_args(argv)

    try:
        cfg = _config_from_args(args)
        source = build_source(cfg)
        fetch = source.fetch()
    except (FileNotFoundError, SourceError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    mapping_cfg = build_mapping(cfg)
    if args.root:
        mapping_cfg.root_path = [p.strip() for p in args.root.split(">") if p.strip()]
    result = map_document(fetch.tree, mapping_cfg)
    report = build_report(fetch, result, mapping_cfg.root_path)

    if args.json:
        print(json.dumps(report.__dict__, ensure_ascii=False, indent=2, default=str))
        return 0

    print(render_report(report))
    for warning in fetch.warnings:
        print(f"\n! {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
