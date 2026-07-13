# -*- coding: utf-8 -*-
"""BM25 + 向量混合检索与 RRF 融合。"""


def rrf_fusion(
    *result_lists: list[dict],
    k: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion，合并多路检索结果。"""
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for results in result_lists:
        for rank, item in enumerate(results):
            key = item["key"]
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            if key not in items:
                items[key] = dict(item)

    fused = []
    for key, score in scores.items():
        row = dict(items[key])
        row["score"] = score
        row["channel"] = "rrf"
        fused.append(row)
    fused.sort(key=lambda x: x["score"], reverse=True)
    return fused
