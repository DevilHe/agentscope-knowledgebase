# -*- coding: utf-8 -*-
"""固定 token 近似切分（utf-8 字节/4 ≈ token）。"""

from __future__ import annotations

from app.ingest.models import Chunk, Section, TextBlock


def approx_token_count(text: str) -> int:
    return len(text.encode("utf-8")) // 4


class ApproxTokenChunker:
    def __init__(self, *, chunk_size: int = 1024, overlap: int = 128) -> None:
        self.chunk_size = max(1, chunk_size)
        self.overlap = max(0, min(overlap, self.chunk_size - 1))

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
            for part in self._split_text(text):
                pieces.append(
                    Chunk(
                        content=TextBlock(text=part),
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

    def _split_text(self, text: str) -> list[str]:
        if approx_token_count(text) <= self.chunk_size:
            return [text]

        # 按字符滑动窗口；overlap 按 token 近似折算为字符
        chars = list(text)
        # 中文约 1 token ≈ 1–2 字；用 token*2 作粗略字符窗口
        window = max(1, self.chunk_size * 2)
        step = max(1, window - self.overlap * 2)
        parts: list[str] = []
        start = 0
        while start < len(chars):
            end = min(len(chars), start + window)
            piece = "".join(chars[start:end]).strip()
            if piece:
                parts.append(piece)
            if end >= len(chars):
                break
            start += step
        return parts or [text]
