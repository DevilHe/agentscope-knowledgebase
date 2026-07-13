import asyncio
from pathlib import Path

from agentscope.rag import ApproxTokenChunker, PDFParser, TextParser

from app.config import settings
from app.db.models import Document as DocumentModel
from app.db.models import SessionLocal
from app.db.redis_client import set_task_status
from app.ingest.chunkers.semantic_token_chunker import SemanticTokenChunker
from app.ingest.parsers.docx_parser import DocxParser
from app.services.chunk_store import delete_chunks_by_doc, insert_chunks
from app.services.knowledge_base import delete_doc_vectors
from app.services.qdrant_hybrid import upsert_chunks

ALLOWED_SUFFIX = {".pdf", ".txt", ".md", ".markdown", ".docx"}


def _pick_parser(suffix: str):
    if suffix == ".pdf":
        return PDFParser()
    if suffix == ".docx":
        return DocxParser()
    return TextParser()


def _get_chunker():
    if settings.chunk_strategy.strip().lower() == "fixed":
        return ApproxTokenChunker(
            chunk_size=settings.chunk_token_size,
            overlap=settings.chunk_token_overlap,
        )
    return SemanticTokenChunker()


async def _cleanup_replaced_doc(replace_doc_id: str, knowledge_base: str) -> None:
    await delete_doc_vectors(replace_doc_id, knowledge_base)
    db = SessionLocal()
    try:
        delete_chunks_by_doc(db, replace_doc_id)
    finally:
        db.close()


async def _run_ingest_async(
    doc_id: str,
    task_id: str,
    file_path: str,
    filename: str,
    knowledge_base: str,
    org_id: str,
    department_id: str | None = None,
    replace_doc_id: str | None = None,
) -> None:
    suffix = Path(file_path).suffix.lower()
    status = "done"
    error = ""
    chunk_count = 0
    try:
        if replace_doc_id:
            await _cleanup_replaced_doc(replace_doc_id, knowledge_base)

        parser = _pick_parser(suffix)
        sections = await parser.parse(file_path, filename)
        raw_chunks = await _get_chunker().chunk(sections)
        for chunk in raw_chunks:
            chunk.metadata["doc_id"] = doc_id
            chunk.metadata["org_id"] = org_id
            if department_id:
                chunk.metadata["department_id"] = department_id

        if not raw_chunks:
            raise ValueError("文档解析后无有效文本内容")

        chunk_rows = []
        hybrid_chunks = []
        total = len(raw_chunks)
        for c in raw_chunks:
            text = c.content.text if hasattr(c.content, "text") else str(c.content)
            source = c.source or filename
            page = c.metadata.get("page") if getattr(c, "metadata", None) else None
            chunk_rows.append((c.chunk_index, source, text))
            hybrid_chunks.append(
                {
                    "chunk_index": c.chunk_index,
                    "source": source,
                    "text": text,
                    "page": page,
                    "total_chunks": total,
                }
            )

        await upsert_chunks(
            doc_id=doc_id,
            knowledge_base=knowledge_base,
            org_id=org_id,
            department_id=department_id,
            chunks=hybrid_chunks,
        )

        db = SessionLocal()
        try:
            # MySQL document_chunks 双写，便于数据备份/调试（检索不再走 MySQL BM25）
            insert_chunks(
                db,
                doc_id=doc_id,
                knowledge_base=knowledge_base,
                org_id=org_id,
                department_id=department_id,
                chunks=chunk_rows,
            )
        finally:
            db.close()

        chunk_count = len(raw_chunks)
    except Exception as exc:
        status = "failed"
        error = str(exc)

    db = SessionLocal()
    try:
        doc = db.get(DocumentModel, doc_id)
        if doc:
            doc.status = status
            doc.chunk_count = chunk_count
            doc.error_message = error or None
            db.commit()
    finally:
        db.close()

    set_task_status(
        task_id,
        {
            "doc_id": doc_id,
            "status": status,
            "chunk_count": chunk_count,
            "error": error or None,
        },
    )


def run_ingest(
    doc_id: str,
    task_id: str,
    file_path: str,
    filename: str,
    knowledge_base: str,
    *,
    org_id: str,
    department_id: str | None = None,
    replace_doc_id: str | None = None,
) -> None:
    asyncio.run(
        _run_ingest_async(
            doc_id,
            task_id,
            file_path,
            filename,
            knowledge_base,
            org_id,
            department_id,
            replace_doc_id=replace_doc_id,
        )
    )
