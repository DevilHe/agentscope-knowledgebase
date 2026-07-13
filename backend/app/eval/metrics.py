# -*- coding: utf-8 -*-
"""RAG 评测指标计算。"""

from __future__ import annotations

from typing import Any


def _chunk_text(item: dict) -> str:
    return (item.get("content") or "").strip()


def _chunk_source(item: dict) -> str:
    return (item.get("source") or "").strip()


def _matches_case(item: dict, case: dict) -> bool:
    content = _chunk_text(item).lower()
    source = _chunk_source(item).lower()

    expected_sources: list[str] = case.get("expected_sources") or []
    expected_keywords: list[str] = case.get("expected_keywords") or []

    source_ok = True
    if expected_sources:
        source_ok = any(exp.lower() in source for exp in expected_sources)

    keyword_ok = True
    if expected_keywords:
        keyword_ok = any(kw.lower() in content for kw in expected_keywords)

    if expected_sources and expected_keywords:
        return source_ok and keyword_ok
    if expected_sources:
        return source_ok
    if expected_keywords:
        return keyword_ok
    return False


def recall_at_k(items: list[dict], case: dict, k: int) -> bool:
    if not case.get("expected_sources") and not case.get("expected_keywords"):
        return True
    for item in items[:k]:
        if _matches_case(item, case):
            return True
    return False


def mrr(items: list[dict], case: dict) -> float:
    if not case.get("expected_sources") and not case.get("expected_keywords"):
        return 1.0
    for rank, item in enumerate(items):
        if _matches_case(item, case):
            return 1.0 / (rank + 1)
    return 0.0


def keyword_coverage(items: list[dict], case: dict, k: int) -> float:
    keywords: list[str] = case.get("expected_keywords") or []
    if not keywords:
        return 1.0
    blob = "\n".join(_chunk_text(item) for item in items[:k]).lower()
    hit = sum(1 for kw in keywords if kw.lower() in blob)
    return hit / len(keywords)


def answer_keyword_coverage(answer: str, case: dict) -> float:
    keywords: list[str] = case.get("expected_answer_keywords") or []
    if not keywords:
        return 1.0
    text = (answer or "").lower()
    hit = sum(1 for kw in keywords if kw.lower() in text)
    return hit / len(keywords)


def summarize_retrieval(results: list[dict[str, Any]]) -> dict[str, float]:
    if not results:
        return {}
    n = len(results)
    return {
        "recall@k": sum(1 for r in results if r["recall@k"]) / n,
        "mrr": sum(r["mrr"] for r in results) / n,
        "keyword_coverage": sum(r["keyword_coverage"] for r in results) / n,
    }


def summarize_full(results: list[dict[str, Any]]) -> dict[str, float]:
    base = summarize_retrieval(results)
    gen_cases = [r for r in results if r.get("answer_keyword_coverage") is not None]
    faith_cases = [r for r in results if r.get("faithful") is not None]
    if gen_cases:
        base["answer_keyword_coverage"] = (
            sum(r["answer_keyword_coverage"] for r in gen_cases) / len(gen_cases)
        )
    if faith_cases:
        base["faithfulness"] = sum(1 for r in faith_cases if r["faithful"]) / len(faith_cases)
        base["hallucination_rate"] = 1.0 - base["faithfulness"]
    return base
