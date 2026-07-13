# -*- coding: utf-8 -*-
"""
LLM 相关性打分 Rerank（0–10）。

实现方式：把 RETRIEVAL_RERANK_CANDIDATES 条片段拼进 prompt，调用 Chat 模型
（OPENAI_MODEL_RERANK / openai_model）一次性打分。典型耗时 **数秒**（与候选数、
模型 RTT 相关），不是 Cohere / bge-reranker 等专用 rerank API 的百毫秒级。

若需亚秒重排，应接入 cross-encoder 或 rerank 专用接口，而非本模块。
"""

import json
import re

from app.services.llm import invoke_text

_SNIPPET_MAX = 400


def _truncate(text: str, limit: int = _SNIPPET_MAX) -> str:
    text = text.strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _build_prompt(query: str, candidates: list[dict]) -> str:
    lines = []
    for i, item in enumerate(candidates):
        lines.append(f"[{i}] {_truncate(item['content'])}")
    body = "\n".join(lines)
    return (
        "你是检索相关性评分助手。根据用户问题，为每条候选文档片段打 0-10 分（10 最相关）。\n\n"
        f"用户问题：{query}\n\n"
        f"候选片段：\n{body}\n\n"
        '请仅输出 JSON 数组，每项格式：{"index": 0, "score": 8}。'
        "index 为候选编号（从 0 开始），score 为 0-10 整数。不要输出其他文字。"
    )


def _parse_scores(raw: str, size: int) -> list[float]:
    match = re.search(r"\[[\s\S]*\]", raw)
    if not match:
        return [0.0] * size
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return [0.0] * size
    scores = [0.0] * size
    if not isinstance(data, list):
        return scores
    for item in data:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        score = item.get("score")
        if isinstance(idx, int) and 0 <= idx < size and isinstance(score, (int, float)):
            scores[idx] = float(max(0, min(10, score)))
    return scores


async def rerank_with_llm(query: str, candidates: list[dict]) -> list[dict]:
    """用 LLM 对候选 chunk 打分并降序排列。"""
    if not candidates:
        return []
    if len(candidates) == 1:
        only = dict(candidates[0])
        only["score"] = 10.0
        only["channel"] = "rerank"
        return [only]

    prompt = _build_prompt(query, candidates)
    raw = await invoke_text(prompt, scene="rerank")
    scores = _parse_scores(raw, len(candidates))

    ranked: list[dict] = []
    for i, item in enumerate(candidates):
        row = dict(item)
        row["score"] = scores[i]
        row["channel"] = "rerank"
        ranked.append(row)
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked
