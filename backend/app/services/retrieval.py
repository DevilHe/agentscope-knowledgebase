# -*- coding: utf-8 -*-
"""
检索管线（MySQL document_chunks 不参与检索）：

  embed 问题
    → Qdrant dense ∥ sparse（并行）→ RRF 融合（rrf）
    → [可选] LLM Rerank（retrieval_rerank_enabled，额外一次 Chat 调用，秒级）
    → top_k 送入 Agent / 引用来源

LLM Rerank 不是毫秒级 cross-encoder；开启后会计入 Agent 工具阶段的「思考用时」。
"""

from app.config import settings
from app.db.models import User
from app.services.acl import (
    allowed_doc_ids_for_retrieval,
    allowed_doc_ids_for_user_retrieval,
    list_retrieval_knowledge_bases,
    resolve_scope,
)
from app.ingest.chunk_policy import chunk_min_retrieval_tokens
from app.services.rerank import rerank_with_llm
from app.services.qdrant_hybrid import point_id as qdrant_point_id


def _content_token_count(text: str) -> int:
    return len((text or "").encode("utf-8")) // 4


def _take_quality_top_k(items: list[dict], top_k: int) -> list[dict]:
    """跳过过短片段，从候选池顺序取满 top_k。"""
    min_tokens = chunk_min_retrieval_tokens()
    if min_tokens <= 0:
        return items[:top_k]
    picked: list[dict] = []
    for item in items:
        if _content_token_count(item.get("content") or "") < min_tokens:
            continue
        picked.append(item)
        if len(picked) >= top_k:
            break
    return picked if picked else items[:top_k]


def _to_sources(items: list[dict]) -> tuple[str, list[dict]]:
    sources: list[dict] = []
    parts: list[str] = []
    for item in items:
        doc_id = item.get("doc_id")
        chunk_index = item.get("chunk_index")
        pid = item.get("point_id")
        if not pid and doc_id is not None and chunk_index is not None:
            pid = qdrant_point_id(str(doc_id), int(chunk_index))
        sources.append(
            {
                "content": item["content"],
                "source": item["source"],
                "score": float(item["score"]),
                "channel": item.get("channel"),
                "point_id": pid,
                "doc_id": doc_id,
                "chunk_index": item.get("chunk_index"),
                "total_chunks": item.get("total_chunks"),
                "page": item.get("page"),
                "key": item.get("key"),
            }
        )
        parts.append(item["content"])
    context = "\n\n---\n\n".join(parts)
    return context, sources


def _resolve_org_id(db, user: User | None) -> str | None:
    if user is None or db is None:
        return None
    return resolve_scope(db, user).org_id


async def _finalize_pipeline(
    question: str,
    vector_items: list[dict],
    bm25_items: list[dict],
    top_k: int,
    *,
    fused: list[dict],
) -> dict:
    # RRF 融合结果取前 N 条做 LLM 重排（invoke_text，典型 3–8s，非百毫秒 reranker）
    quality_fused = _take_quality_top_k(fused, max(top_k * 3, settings.retrieval_rerank_candidates))
    rerank_pool = quality_fused[: settings.retrieval_rerank_candidates]

    if settings.retrieval_rerank_enabled and rerank_pool:
        final_items = await rerank_with_llm(question, rerank_pool)
    else:
        final_items = rerank_pool

    return {
        "vector": vector_items,
        "bm25": bm25_items,
        "rrf": fused,
        "final": _take_quality_top_k(final_items, top_k),
    }


async def _retrieve_pipeline_qdrant(
    question: str,
    top_k: int,
    *,
    knowledge_base: str | None = None,
    knowledge_bases: list[str] | None = None,
    allowed_doc_ids: set[str] | None = None,
    org_id: str | None = None,
) -> dict:
    from app.services import qdrant_hybrid as qh

    candidate_k = settings.retrieval_candidate_top_k
    if not settings.retrieval_hybrid_enabled:
        vector_items = await qh.search_dense(
            question,
            max(top_k * 2, candidate_k),
            org_id=org_id,
            knowledge_base=knowledge_base,
            knowledge_bases=knowledge_bases,
            allowed_doc_ids=allowed_doc_ids,
        )
        final_items = _take_quality_top_k(vector_items, top_k)
        return {
            "vector": vector_items,
            "bm25": [],
            "rrf": final_items,
            "final": final_items,
        }

    parts = await qh.search_hybrid(
        question,
        top_k,
        candidate_k=candidate_k,
        org_id=org_id,
        knowledge_base=knowledge_base,
        knowledge_bases=knowledge_bases,
        allowed_doc_ids=allowed_doc_ids,
    )
    return await _finalize_pipeline(
        question,
        parts["vector"],
        parts["bm25"],
        top_k,
        fused=parts["rrf"],
    )


async def retrieve_sources(
    question: str,
    knowledge_base: str,
    top_k: int,
    *,
    user: User | None = None,
    db=None,
) -> tuple[str, list[dict]]:
    allowed_doc_ids = None
    if user is not None and db is not None:
        allowed_doc_ids = allowed_doc_ids_for_retrieval(db, user, knowledge_base)
    pipeline = await _retrieve_pipeline(
        question,
        knowledge_base,
        top_k,
        allowed_doc_ids=allowed_doc_ids,
        db=db,
        user=user,
    )
    return _to_sources(pipeline["final"])


async def retrieve_sources_for_user(
    question: str,
    top_k: int,
    *,
    user: User,
    db,
) -> tuple[str, list[dict]]:
    kb_slugs = list_retrieval_knowledge_bases(db, user)
    allowed_doc_ids = allowed_doc_ids_for_user_retrieval(db, user)
    pipeline = await _retrieve_pipeline_for_user(
        question,
        kb_slugs,
        top_k,
        allowed_doc_ids=allowed_doc_ids,
        db=db,
        user=user,
    )
    return _to_sources(pipeline["final"])


async def retrieve_detailed(
    question: str,
    knowledge_base: str,
    top_k: int,
    *,
    user: User | None = None,
    db=None,
) -> dict:
    """返回各检索阶段结果，供评测脚本使用。"""
    allowed_doc_ids = None
    if user is not None and db is not None:
        allowed_doc_ids = allowed_doc_ids_for_retrieval(db, user, knowledge_base)
    pipeline = await _retrieve_pipeline(
        question,
        knowledge_base,
        top_k,
        allowed_doc_ids=allowed_doc_ids,
        db=db,
        user=user,
    )
    context, sources = _to_sources(pipeline["final"])
    return {
        **pipeline,
        "context": context,
        "sources": sources,
    }


async def _retrieve_pipeline(
    question: str,
    knowledge_base: str,
    top_k: int,
    *,
    allowed_doc_ids: set[str] | None = None,
    db=None,
    user: User | None = None,
) -> dict:
    return await _retrieve_pipeline_qdrant(
        question,
        top_k,
        knowledge_base=knowledge_base,
        allowed_doc_ids=allowed_doc_ids,
        org_id=_resolve_org_id(db, user),
    )


async def _retrieve_pipeline_for_user(
    question: str,
    kb_slugs: list[str],
    top_k: int,
    *,
    allowed_doc_ids: set[str] | None,
    db,
    user: User | None = None,
) -> dict:
    if not kb_slugs:
        return {"vector": [], "bm25": [], "rrf": [], "final": []}

    return await _retrieve_pipeline_qdrant(
        question,
        top_k,
        knowledge_bases=kb_slugs,
        allowed_doc_ids=allowed_doc_ids,
        org_id=_resolve_org_id(db, user),
    )
