# -*- coding: utf-8 -*-
"""MySQL FULLTEXT 分块存储与 BM25 检索。"""

import re
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk


def chunk_key(doc_id: str, chunk_index: int) -> str:
    return f"{doc_id}:{chunk_index}"


def insert_chunks(
    db: Session,
    *,
    doc_id: str,
    knowledge_base: str,
    org_id: str | None = None,
    department_id: str | None = None,
    chunks: list[tuple[int, str, str]],
) -> None:
    """批量写入分块（chunk_index, source, content）。"""
    delete_chunks_by_doc(db, doc_id)
    rows = [
        DocumentChunk(
            id=str(uuid.uuid4()),
            doc_id=doc_id,
            knowledge_base=knowledge_base,
            org_id=org_id,
            department_id=department_id,
            chunk_index=idx,
            source=source,
            content=content,
        )
        for idx, source, content in chunks
    ]
    db.add_all(rows)
    db.commit()


def delete_chunks_by_doc(db: Session, doc_id: str) -> None:
    db.query(DocumentChunk).filter(DocumentChunk.doc_id == doc_id).delete()
    db.commit()


def _boolean_query(query: str) -> str:
    terms = [t for t in re.split(r"[\s\W_]+", query.strip()) if len(t) >= 1]
    if not terms:
        return query
    return " ".join(f"+{term}" for term in terms[:12])


def search_bm25(
    db: Session,
    query: str,
    knowledge_base: str,
    top_k: int,
    allowed_doc_ids: set[str] | None = None,
) -> list[dict]:
    """MySQL FULLTEXT 检索，返回 BM25 风格相关度分数。"""
    return _search_bm25_query(db, query, top_k, knowledge_base=knowledge_base, allowed_doc_ids=allowed_doc_ids)


def search_bm25_scoped(
    db: Session,
    query: str,
    top_k: int,
    allowed_doc_ids: set[str] | None = None,
) -> list[dict]:
    """按用户权限跨知识库 BM25 检索。"""
    return _search_bm25_query(db, query, top_k, knowledge_base=None, allowed_doc_ids=allowed_doc_ids)


def _search_bm25_query(
    db: Session,
    query: str,
    top_k: int,
    *,
    knowledge_base: str | None,
    allowed_doc_ids: set[str] | None,
) -> list[dict]:
    if not query.strip():
        return []
    if allowed_doc_ids is not None and not allowed_doc_ids:
        return []

    doc_filter = ""
    kb_filter = ""
    params: dict = {"q": query, "limit": top_k}
    if knowledge_base is not None:
        kb_filter = " AND knowledge_base = :kb"
        params["kb"] = knowledge_base
    if allowed_doc_ids is not None:
        placeholders = ", ".join(f":doc{i}" for i in range(len(allowed_doc_ids)))
        doc_filter = f" AND doc_id IN ({placeholders})"
        for i, doc_id in enumerate(sorted(allowed_doc_ids)):
            params[f"doc{i}"] = doc_id

    rows = db.execute(
        text(
            f"""
            SELECT doc_id, chunk_index, source, content,
                   MATCH(content) AGAINST(:q IN NATURAL LANGUAGE MODE) AS score
            FROM document_chunks
            WHERE MATCH(content) AGAINST(:q IN NATURAL LANGUAGE MODE)
              {kb_filter}
              {doc_filter}
            ORDER BY score DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    if not rows:
        bool_q = _boolean_query(query)
        params["q"] = bool_q
        rows = db.execute(
            text(
                f"""
                SELECT doc_id, chunk_index, source, content,
                       MATCH(content) AGAINST(:q IN BOOLEAN MODE) AS score
                FROM document_chunks
                WHERE MATCH(content) AGAINST(:q IN BOOLEAN MODE)
                  {kb_filter}
                  {doc_filter}
                ORDER BY score DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()

    results: list[dict] = []
    for row in rows:
        score = float(row["score"] or 0)
        if score <= 0:
            continue
        doc_id = row["doc_id"]
        chunk_index = int(row["chunk_index"])
        results.append(
            {
                "key": chunk_key(doc_id, chunk_index),
                "doc_id": doc_id,
                "chunk_index": chunk_index,
                "source": row["source"] or "unknown",
                "content": row["content"],
                "score": score,
                "channel": "bm25",
            }
        )
    return results
