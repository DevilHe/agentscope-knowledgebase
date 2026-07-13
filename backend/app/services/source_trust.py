# -*- coding: utf-8 -*-
"""引用来源可信度过滤。"""

from __future__ import annotations

import re

_EXPLICIT_REFUSAL_MARKERS = (
    "未找到相关知识库内容",
    "资料不足以回答",
    "无法从参考资料",
    "无法根据提供的资料",
    "没有足够的信息",
    "未在知识库中找到",
    "未找到关于",
    "未找到与",
    "没有找到",
    "未检索到",
    "没有涉及",
    "但没有涉及",
    "并未包含",
    "未包含",
    "知识库中没有",
    "知识库中并没有",
    "无法从知识库",
    "根据知识库检索结果，未找到",
)

_REFUSAL_PATTERNS = (
    re.compile(r"未找到.{0,40}相关"),
    re.compile(r"没有.{0,20}(涉及|包含)"),
    re.compile(r"知识库中.{0,30}没有"),
    re.compile(r"无法.{0,20}(回答|提供).{0,20}(信息|内容)"),
)

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]{2,}")


def _normalize_tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")}


def is_refusal_answer(answer: str) -> bool:
    """回答是否表明知识库未命中有效内容。"""
    normalized = (answer or "").strip()
    if not normalized:
        return True
    if any(marker in normalized for marker in _EXPLICIT_REFUSAL_MARKERS):
        return True
    return any(pattern.search(normalized) for pattern in _REFUSAL_PATTERNS)


def _answer_supported_by_sources(answer: str, sources: list[dict]) -> bool:
    """答案与引用片段是否存在足够文本重叠（避免检索了但回答完全跑偏仍展示引用）。"""
    answer_tokens = _normalize_tokens(answer)
    if len(answer_tokens) < 4:
        return bool(sources)

    source_tokens: set[str] = set()
    for item in sources:
        source_tokens |= _normalize_tokens(item.get("content") or "")

    if not source_tokens:
        return False

    shared = answer_tokens & source_tokens
    if not shared:
        return False
    # 10% 词重叠；LLM 改写后常低于该比例，至少 2 个词命中仍展示引用
    overlap = len(shared) / len(answer_tokens)
    return overlap >= 0.1 or len(shared) >= 2


def _dedupe_sources(sources: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for item in sources:
        key = item.get("point_id") or item.get("key") or f"{item.get('doc_id', '')}:{item.get('chunk_index', '')}:{item.get('source', '')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def effective_sources(answer: str, sources: list[dict]) -> list[dict]:
    if not sources:
        return []

    cleaned = _dedupe_sources(sources)
    if is_refusal_answer(answer):
        return []
    if not _answer_supported_by_sources(answer, cleaned):
        return []
    return cleaned


def sources_view(answer: str, sources: list[dict] | None) -> dict:
    """接口层引用展示：由后端统一判定是否展示引用。"""
    items = effective_sources(answer, sources or [])
    return {"show_sources": bool(items), "items": items}
