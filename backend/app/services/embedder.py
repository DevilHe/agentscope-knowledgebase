"""Embedding：Ollama HTTP API（nomic-embed-text 等）。"""

from __future__ import annotations

import httpx

from app.config import settings


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量嵌入；返回与 texts 等长的向量列表。"""
    if not texts:
        return []

    base = settings.ollama_base_url.rstrip("/")
    url = f"{base}/api/embed"
    payload = {
        "model": settings.embedding_model,
        "input": texts,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    embeddings = data.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        return embeddings

    # 兼容旧 /api/embeddings 单条接口回退
    vectors: list[list[float]] = []
    legacy_url = f"{base}/api/embeddings"
    async with httpx.AsyncClient(timeout=120.0) as client:
        for text in texts:
            resp = await client.post(
                legacy_url,
                json={"model": settings.embedding_model, "prompt": text},
            )
            resp.raise_for_status()
            body = resp.json()
            vectors.append(body["embedding"])
    return vectors
