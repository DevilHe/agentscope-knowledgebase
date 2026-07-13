# -*- coding: utf-8 -*-
"""Qdrant 原生 dense + sparse 混合检索（单 collection + payload 隔离）。"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.config import settings
from app.services.chunk_store import chunk_key
from app.services.embedder import embed_texts
from app.services.sparse_text import text_to_sparse

DENSE_NAME = "dense"
SPARSE_NAME = "sparse"

_client: AsyncQdrantClient | None = None


def hybrid_collection_name() -> str:
    base = settings.qdrant_collection.strip() or "standards"
    suffix = (settings.qdrant_hybrid_collection_suffix or "").strip()
    return f"{base}{suffix}" if suffix else f"{base}_hybrid"


def get_async_qdrant() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(url=settings.qdrant_url)
    return _client


def point_id(doc_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:{chunk_index}"))


def build_payload_filter(
    *,
    org_id: str | None = None,
    knowledge_base: str | None = None,
    knowledge_bases: list[str] | None = None,
    allowed_doc_ids: set[str] | None = None,
) -> qmodels.Filter | None:
    """强制 payload 过滤；allowed_doc_ids 为空集合表示无权限。"""
    must: list[qmodels.FieldCondition | qmodels.Filter] = []

    if org_id:
        must.append(
            qmodels.FieldCondition(
                key="org_id",
                match=qmodels.MatchValue(value=org_id),
            )
        )

    if knowledge_base:
        must.append(
            qmodels.FieldCondition(
                key="knowledge_base",
                match=qmodels.MatchValue(value=knowledge_base),
            )
        )
    elif knowledge_bases is not None:
        if not knowledge_bases:
            return qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="doc_id",
                        match=qmodels.MatchValue(value="__none__"),
                    )
                ]
            )
        must.append(
            qmodels.FieldCondition(
                key="knowledge_base",
                match=qmodels.MatchAny(any=list(knowledge_bases)),
            )
        )

    if allowed_doc_ids is not None:
        if not allowed_doc_ids:
            return qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="doc_id",
                        match=qmodels.MatchValue(value="__none__"),
                    )
                ]
            )
        must.append(
            qmodels.FieldCondition(
                key="doc_id",
                match=qmodels.MatchAny(any=sorted(allowed_doc_ids)),
            )
        )

    if not must:
        return None
    return qmodels.Filter(must=must)


async def ensure_hybrid_collection() -> None:
    client = get_async_qdrant()
    name = hybrid_collection_name()
    exists = await client.collection_exists(name)
    if not exists:
        await client.create_collection(
            collection_name=name,
            vectors_config={
                DENSE_NAME: qmodels.VectorParams(
                    size=settings.embedding_dimensions,
                    distance=qmodels.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                SPARSE_NAME: qmodels.SparseVectorParams(
                    index=qmodels.SparseIndexParams(on_disk=False),
                )
            },
        )

    for field in ("org_id", "tenant_id", "knowledge_base", "doc_id", "document_id"):
        try:
            await client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            # 索引已存在时忽略
            pass


async def delete_document(doc_id: str) -> None:
    client = get_async_qdrant()
    name = hybrid_collection_name()
    if not await client.collection_exists(name):
        return
    await client.delete(
        collection_name=name,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                should=[
                    qmodels.FieldCondition(
                        key="document_id",
                        match=qmodels.MatchValue(value=doc_id),
                    ),
                    qmodels.FieldCondition(
                        key="doc_id",
                        match=qmodels.MatchValue(value=doc_id),
                    ),
                ]
            )
        ),
    )


async def upsert_chunks(
    *,
    doc_id: str,
    knowledge_base: str,
    org_id: str,
    department_id: str | None,
    chunks: list[dict[str, Any]],
) -> None:
    """
    chunks: [{chunk_index, source, text, page?, total_chunks?}, ...]
    """
    if not chunks:
        return
    await ensure_hybrid_collection()
    texts = [str(c.get("text") or "") for c in chunks]
    dense_vectors = await embed_texts(texts)

    points: list[qmodels.PointStruct] = []
    for chunk, dense in zip(chunks, dense_vectors):
        text = str(chunk.get("text") or "")
        chunk_index = int(chunk["chunk_index"])
        source = str(chunk.get("source") or "")
        payload: dict[str, Any] = {
            "document_id": doc_id,
            "doc_id": doc_id,
            "org_id": org_id,
            "tenant_id": org_id,
            "knowledge_base": knowledge_base,
            "department_id": department_id,
            "chunk_index": chunk_index,
            "total_chunks": int(chunk.get("total_chunks") or 0),
            "page": chunk.get("page"),
            "source": source,
            "text": text,
        }
        points.append(
            qmodels.PointStruct(
                id=point_id(doc_id, chunk_index),
                vector={
                    DENSE_NAME: dense,
                    SPARSE_NAME: text_to_sparse(text),
                },
                payload=payload,
            )
        )

    await get_async_qdrant().upsert(
        collection_name=hybrid_collection_name(),
        points=points,
    )


def _format_point_id(raw: object | None, doc_id: str, chunk_index: int) -> str:
    if raw is not None:
        return str(raw)
    return point_id(doc_id, chunk_index)


def _point_to_item(point: qmodels.ScoredPoint, channel: str) -> dict[str, Any] | None:
    payload = point.payload or {}
    doc_id = str(payload.get("doc_id") or payload.get("document_id") or "")
    if not doc_id:
        return None
    chunk_index = int(payload.get("chunk_index") or 0)
    page = payload.get("page")
    pid = _format_point_id(getattr(point, "id", None), doc_id, chunk_index)
    return {
        "key": chunk_key(doc_id, chunk_index),
        "point_id": pid,
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "total_chunks": int(payload.get("total_chunks") or 0),
        "page": int(page) if page is not None else None,
        "source": payload.get("source") or "unknown",
        "content": payload.get("text") or "",
        "score": float(point.score or 0.0),
        "channel": channel,
    }


async def search_dense(
    question: str,
    top_k: int,
    *,
    org_id: str | None = None,
    knowledge_base: str | None = None,
    knowledge_bases: list[str] | None = None,
    allowed_doc_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    await ensure_hybrid_collection()
    query_filter = build_payload_filter(
        org_id=org_id,
        knowledge_base=knowledge_base,
        knowledge_bases=knowledge_bases,
        allowed_doc_ids=allowed_doc_ids,
    )
    dense = (await embed_texts([question]))[0]
    response = await get_async_qdrant().query_points(
        collection_name=hybrid_collection_name(),
        query=dense,
        using=DENSE_NAME,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    )
    items: list[dict[str, Any]] = []
    for point in response.points:
        item = _point_to_item(point, "vector")
        if item:
            items.append(item)
    return items


async def search_hybrid(
    question: str,
    top_k: int,
    *,
    candidate_k: int | None = None,
    org_id: str | None = None,
    knowledge_base: str | None = None,
    knowledge_bases: list[str] | None = None,
    allowed_doc_ids: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    混合检索：dense（向量）+ sparse（BM25 风格）→ Qdrant RRF 融合。

    - 向量与 sparse 在 Qdrant 侧通过 FusionQuery prefetch **并行**召回后再 RRF。
    - 另发起独立的 dense / sparse 查询仅用于评测脚本对比各阶段 recall（与融合查询并行发出）。
    """
    await ensure_hybrid_collection()
    limit = max(top_k, candidate_k or settings.retrieval_candidate_top_k)
    query_filter = build_payload_filter(
        org_id=org_id,
        knowledge_base=knowledge_base,
        knowledge_bases=knowledge_bases,
        allowed_doc_ids=allowed_doc_ids,
    )

    dense = (await embed_texts([question]))[0]
    sparse = text_to_sparse(question)

    dense_resp, sparse_resp, fused_resp = await _search_parts(
        dense=dense,
        sparse=sparse,
        limit=limit,
        query_filter=query_filter,
    )

    vector_items = []
    for point in dense_resp.points:
        item = _point_to_item(point, "vector")
        if item:
            vector_items.append(item)

    bm25_items = []
    for point in sparse_resp.points:
        item = _point_to_item(point, "bm25")
        if item:
            bm25_items.append(item)

    rrf_items = []
    for point in fused_resp.points:
        item = _point_to_item(point, "rrf")
        if item:
            rrf_items.append(item)

    return {
        "vector": vector_items,
        "bm25": bm25_items,
        "rrf": rrf_items,
    }


async def _search_parts(
    *,
    dense: list[float],
    sparse: qmodels.SparseVector,
    limit: int,
    query_filter: qmodels.Filter | None,
):
    """
    向 Qdrant 发起三路查询（asyncio 并行，避免串行等待）：

    1. dense  — 向量相似度（channel=vector）
    2. sparse — 稀疏/BM25 风格（channel=bm25）
    3. fused  — prefetch dense+sparse 后服务端 RRF 融合（channel=rrf，对话检索实际使用）

    说明：fused 的 prefetch 在 Qdrant 内部已是并行；1/2 仅为 eval 分阶段指标，
    与 3 同时发出，不增加「先 vector 再 bm25 再融合」的串行延迟。
    """
    client = get_async_qdrant()
    name = hybrid_collection_name()

    dense_req = client.query_points(
        collection_name=name,
        query=dense,
        using=DENSE_NAME,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )
    sparse_req = client.query_points(
        collection_name=name,
        query=sparse,
        using=SPARSE_NAME,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )
    fused_req = client.query_points(
        collection_name=name,
        prefetch=[
            qmodels.Prefetch(
                query=dense,
                using=DENSE_NAME,
                filter=query_filter,
                limit=limit,
            ),
            qmodels.Prefetch(
                query=sparse,
                using=SPARSE_NAME,
                filter=query_filter,
                limit=limit,
            ),
        ],
        query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
        limit=limit,
        with_payload=True,
    )
    return await asyncio.gather(dense_req, sparse_req, fused_req)
