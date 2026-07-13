# -*- coding: utf-8 -*-
"""Agent Prompt 版本管理与灰度发布。"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from app.config import settings

_PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts" / "unified_agent"
_FALLBACK_PROMPT = """你是「AI 知识库助手」。请根据用户问题与工具检索结果作答，不要编造。"""


@lru_cache(maxsize=16)
def _load_prompt_file(version: str) -> str:
    path = _PROMPT_ROOT / f"{version}.txt"
    if not path.is_file():
        return _FALLBACK_PROMPT
    return path.read_text(encoding="utf-8").strip()


def _in_canary(user_id: str | None) -> bool:
    percent = max(0, min(100, settings.agent_prompt_canary_percent))
    if percent <= 0 or not settings.agent_prompt_canary_version:
        return False
    if not user_id:
        return False
    bucket = int(hashlib.sha256(user_id.encode()).hexdigest()[:8], 16) % 100
    return bucket < percent


def resolve_system_prompt(user_id: str | None = None) -> tuple[str, str]:
    """返回 (prompt 正文, 生效版本号)。"""
    stable = settings.agent_prompt_version or "v1"
    if _in_canary(user_id):
        version = settings.agent_prompt_canary_version
        return _load_prompt_file(version), version
    return _load_prompt_file(stable), stable
