# -*- coding: utf-8 -*-
"""
Embedding 语义分块 + 固定 token 切块兜底。

在满足语义边界前提下，单块尽量落在 512–1024 token（由 CHUNK_TOKEN_SIZE 控制上限）。
"""

from __future__ import annotations

import logging
import math
import re

from app.config import settings
from app.ingest.chunk_policy import (
    EMBED_BATCH_SIZE,
    chunk_max_tokens,
    chunk_min_tokens,
    chunk_min_unit_tokens,
)
from app.ingest.chunkers.approx_token_chunker import ApproxTokenChunker, approx_token_count
from app.ingest.models import Chunk, Section, TextBlock
from app.services.embedder import embed_texts

logger = logging.getLogger(__name__)

_ARTICLE_BREAK = re.compile(r"(?=第[一二三四五六七八九十百零\d]+条)")
_SENTENCE_END = re.compile(r"(?<=[。！？])")


def _merge_tiny_units(units: list[str], min_tokens: int) -> list[str]:
    """过短单元与前后合并，避免列表项单独成块。"""
    if not units or min_tokens <= 0:
        return units
    merged: list[str] = []
    i = 0
    max_size = chunk_max_tokens()
    while i < len(units):
        cur = units[i]
        while (
            i + 1 < len(units)
            and approx_token_count(cur) < min_tokens
            and approx_token_count(cur + units[i + 1]) <= max_size
        ):
            i += 1
            cur += units[i]
        merged.append(cur)
        i += 1
    return merged


def split_semantic_units(text: str) -> list[str]:
    """将段落拆成适合算相邻相似度的语义单元。"""
    text = (text or "").strip()
    if not text:
        return []

    units: list[str] = []
    for article in _ARTICLE_BREAK.split(text):
        article = article.strip()
        if not article:
            continue
        if approx_token_count(article) <= max(32, settings.chunk_token_size // 4):
            units.append(article)
            continue
        parts = _SENTENCE_END.split(article)
        buf = ""
        for part in parts:
            if not part:
                continue
            buf += part
            if part.rstrip().endswith(("。", "！", "？")):
                piece = buf.strip()
                if piece:
                    units.append(piece)
                buf = ""
        if buf.strip():
            units.append(buf.strip())

    units = _merge_tiny_units(units, chunk_min_unit_tokens())
    if not units:
        return [text]
    return units


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SemanticTokenChunker:
    """语义分块；超长或 embed 失败时回退 ApproxTokenChunker。"""

    def __init__(
        self,
        *,
        chunk_size: int | None = None,
        overlap: int | None = None,
        similarity_threshold: float | None = None,
        min_chunk_tokens: int | None = None,
        embed_batch_size: int | None = None,
    ) -> None:
        self.chunk_size = chunk_size if chunk_size is not None else chunk_max_tokens()
        self.overlap = overlap if overlap is not None else settings.chunk_token_overlap
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else settings.chunk_semantic_similarity_threshold
        )
        self.min_chunk_tokens = (
            min_chunk_tokens if min_chunk_tokens is not None else chunk_min_tokens()
        )
        self.embed_batch_size = (
            embed_batch_size if embed_batch_size is not None else EMBED_BATCH_SIZE
        )
        self._fixed = ApproxTokenChunker(chunk_size=self.chunk_size, overlap=self.overlap)

    async def chunk(self, sections: list[Section]) -> list[Chunk]:
        pieces: list[Chunk] = []
        for section in sections:
            text = (
                section.content.text
                if isinstance(section.content, TextBlock)
                else str(section.content)
            )
            text = (text or "").strip()
            if not text:
                continue

            for piece_text in await self._split_section_text(text):
                if approx_token_count(piece_text) > self.chunk_size:
                    pieces.extend(
                        await self._fixed.chunk(
                            [
                                Section(
                                    content=TextBlock(text=piece_text),
                                    source=section.source,
                                    metadata=dict(section.metadata),
                                )
                            ]
                        )
                    )
                else:
                    pieces.append(
                        Chunk(
                            content=TextBlock(text=piece_text),
                            source=section.source,
                            chunk_index=0,
                            total_chunks=0,
                            metadata=dict(section.metadata),
                        )
                    )

        for index, chunk in enumerate(pieces):
            chunk.chunk_index = index
            chunk.total_chunks = len(pieces)
        return pieces

    async def _split_section_text(self, text: str) -> list[str]:
        units = split_semantic_units(text)
        if len(units) <= 1:
            return units if units else [text]

        try:
            embeddings = await self._embed_units(units)
        except Exception as exc:
            logger.warning("语义分块 embedding 失败，回退固定 token 切分: %s", exc)
            return [text]

        groups = self._group_units(units, embeddings)
        groups = self._merge_undersized_groups(groups)
        return ["".join(g) for g in groups if "".join(g).strip()]

    def _group_units(
        self, units: list[str], embeddings: list[list[float]]
    ) -> list[list[str]]:
        groups: list[list[str]] = [[units[0]]]
        for i in range(1, len(units)):
            sim = cosine_similarity(embeddings[i - 1], embeddings[i])
            merged = "".join(groups[-1]) + units[i]
            current_tokens = approx_token_count("".join(groups[-1]))
            too_large = approx_token_count(merged) > self.chunk_size
            topic_shift = sim < self.similarity_threshold
            need_more = current_tokens < self.min_chunk_tokens

            if too_large:
                groups.append([units[i]])
            elif need_more or not topic_shift:
                groups[-1].append(units[i])
            else:
                groups.append([units[i]])
        return groups

    def _merge_undersized_groups(self, groups: list[list[str]]) -> list[list[str]]:
        if self.min_chunk_tokens <= 0 or len(groups) <= 1:
            return groups

        merged: list[list[str]] = []
        i = 0
        while i < len(groups):
            current = list(groups[i])
            while (
                i + 1 < len(groups)
                and approx_token_count("".join(current)) < self.min_chunk_tokens
                and approx_token_count("".join(current) + "".join(groups[i + 1]))
                <= self.chunk_size
            ):
                i += 1
                current.extend(groups[i])
            merged.append(current)
            i += 1
        return merged

    async def _embed_units(self, units: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        batch = max(1, self.embed_batch_size)
        for start in range(0, len(units), batch):
            batch_units = units[start : start + batch]
            vectors.extend(await embed_texts(batch_units))
        if len(vectors) != len(units):
            raise RuntimeError(f"embedding 数量不匹配: {len(vectors)} vs {len(units)}")
        return vectors
