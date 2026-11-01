"""打开数据源：Markdown 用系统默认程序，幕布尽量唤起客户端。

面板点文字、设置面板点「打开数据源」都走这里。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .sources.mubu import DATA_ROOT, normalize_doc_id


def open_source(source: dict) -> str | None:
    """打开成功返回 None，失败返回一句人话原因。"""
    kind = (source or {}).get("type")

    if kind == "markdown":
        path = Path(source.get("path", ""))
        if not path.exists():
            return f"文件不存在：{path}"
        try:
            os.startfile(str(path))  # noqa: S606 - 打开用户自己的文件
        except OSError as exc:
            return f"打不开：{exc}"
        return None

    if kind == "mubu":
        doc_id = normalize_doc_id(source.get("docId", ""))
        exe = source.get("mubuExe")
        if exe and Path(exe).exists():
            try:
                subprocess.Popen([exe, f"shortcut-{doc_id}"], close_fds=True)
                return None
            except OSError as exc:
                return f"启动幕布失败：{exc}"
        # 没配客户端路径就退而求其次，打开本地备份目录
        folder = DATA_ROOT / "backup" / doc_id
        if folder.is_dir():
            try:
                os.startfile(str(folder))  # noqa: S606
                return None
            except OSError as exc:
                return f"打不开备份目录：{exc}"
        return "没找到幕布客户端路径，也没有本地备份"

    return "这个数据源不支持直接打开"
