# -*- coding: utf-8 -*-
"""向量侧封装：入库/检索走自研 Qdrant hybrid。"""

from qdrant_client.http import models as qmodels

from app.config import settings
from app.services.qdrant_hybrid import get_async_qdrant


async def ensure_collection() -> None:
    from app.services.qdrant_hybrid import ensure_hybrid_collection

    await ensure_hybrid_collection()


async def delete_doc_vectors(doc_id: str, knowledge_base: str) -> None:
    """删除 Qdrant 中该文档的全部向量（hybrid + 旧版 dense collection）。"""
    del knowledge_base  # 兼容旧调用签名
    from app.services.qdrant_hybrid import delete_document as hybrid_delete

    await hybrid_delete(doc_id)

    # 清理旧版 dense-only collection（如 standards）
    client = get_async_qdrant()
    legacy = settings.qdrant_collection.strip() or "standards"
    if await client.collection_exists(legacy):
        await client.delete(
            collection_name=legacy,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="doc_id",
                            match=qmodels.MatchValue(value=doc_id),
                        )
                    ]
                )
            ),
        )


def vector_score_threshold() -> float:
    """与历史 score_threshold 配置兼容：相似度下限 = 1 - score_threshold。"""
    return 1.0 - settings.score_threshold
