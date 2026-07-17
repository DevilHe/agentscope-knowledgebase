# -*- coding: utf-8 -*-
"""上传文件落盘路径：保留原始文件名，按知识库分目录。"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import settings

_UNSAFE = re.compile(r'[\x00-\x1f<>:"|?*\\/]')


def sanitize_filename(filename: str) -> str:
    """只保留 basename，并去掉危险字符。"""
    name = Path(filename or "").name.strip()
    if not name or name in {".", ".."}:
        return "unnamed"
    name = _UNSAFE.sub("_", name).strip(" .")
    return name or "unnamed"


def upload_kb_dir(knowledge_base: str) -> Path:
    kb = sanitize_filename(knowledge_base or "default")
    path = settings.resolved_upload_dir / kb
    path.mkdir(parents=True, exist_ok=True)
    return path


def stored_upload_path(knowledge_base: str, filename: str) -> Path:
    """目标落盘路径：uploads/{kb}/{原始文件名}。"""
    return upload_kb_dir(knowledge_base) / sanitize_filename(filename)


def resolve_stored_file(filename: str, knowledge_base: str) -> Path | None:
    """查找已落盘文件：uploads/{kb}/{原始文件名}。"""
    path = stored_upload_path(knowledge_base, filename)
    return path if path.is_file() else None


def remove_stored_file(filename: str, knowledge_base: str) -> None:
    """删除落盘文件。"""
    path = resolve_stored_file(filename, knowledge_base)
    if path and path.is_file():
        path.unlink(missing_ok=True)
