# -*- coding: utf-8 -*-
"""Agent Prompt 版本管理与灰度发布。

从 app/prompts/prompts.yml 加载 unified_agent 各版本 system_prompt。
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import settings

_PROMPTS_YML = Path(__file__).resolve().parents[1] / "prompts" / "prompts.yml"
_FALLBACK_PROMPT = """你是「AI 知识库助手」。请根据用户问题与工具检索结果作答，不要编造。"""


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _prompt_catalog() -> dict[str, Any]:
    if not _PROMPTS_YML.is_file():
        return {}
    return _load_yaml(_PROMPTS_YML)


@lru_cache(maxsize=16)
def _load_prompt(version: str) -> str:
    catalog = _prompt_catalog()
    versions = catalog.get("unified_agent") or {}
    entry = versions.get(version)
    if isinstance(entry, dict):
        text = entry.get("system_prompt") or ""
    elif isinstance(entry, str):
        text = entry
    else:
        text = ""
    text = text.strip()
    return text or _FALLBACK_PROMPT


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
        return _load_prompt(version), version
    return _load_prompt(stable), stable
