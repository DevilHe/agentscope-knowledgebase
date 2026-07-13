# -*- coding: utf-8 -*-
"""向量侧封装：入库/检索走 Qdrant hybrid；AgentScope KnowledgeBase 仅作兼容保留。"""

from agentscope.rag import KnowledgeBase

from app.config import settings
from app.services.embedder import get_embedder
from app.services.vectorstore import get_vector_store

_kb_cache: dict[str, KnowledgeBase] = {}


def get_knowledge_base(knowledge_base: str) -> KnowledgeBase:
    if knowledge_base not in _kb_cache:
        _kb_cache[knowledge_base] = KnowledgeBase(
            name=knowledge_base,
            description=f"知识库 {knowledge_base}",
            embedding_model=get_embedder(),
            vector_store=get_vector_store(),
            collection=settings.qdrant_collection,
            metadata_filter={"knowledge_base": knowledge_base},
        )
    return _kb_cache[knowledge_base]


async def ensure_collection() -> None:
    from app.services.qdrant_hybrid import ensure_hybrid_collection

    await ensure_hybrid_collection()


async def delete_doc_vectors(doc_id: str, knowledge_base: str) -> None:
    """删除 Qdrant 中该文档的全部向量（hybrid + 旧版 dense collection）。"""
    del knowledge_base  # 兼容旧调用签名
    from app.services.qdrant_hybrid import delete_document as hybrid_delete

    await hybrid_delete(doc_id)

    # 旧版 AgentScope 入库写入 settings.qdrant_collection（如 standards）
    store = get_vector_store()
    client = store.get_client()
    if await client.collection_exists(settings.qdrant_collection):
        await store.delete(settings.qdrant_collection, doc_id)


def vector_score_threshold() -> float:
    """与历史 score_threshold 配置兼容：相似度下限 = 1 - score_threshold。"""
    return 1.0 - settings.score_threshold
