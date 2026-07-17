# -*- coding: utf-8 -*-
"""纯文本 / Markdown 解析。"""

from __future__ import annotations

from pathlib import Path

from app.ingest.models import Section, TextBlock


class TextParser:
    async def parse(self, file: bytes | str, filename: str) -> list[Section]:
        if isinstance(file, str):
            text = Path(file).read_text(encoding="utf-8", errors="ignore")
        else:
            text = file.decode("utf-8", errors="ignore")
        text = (text or "").strip()
        if not text:
            return []
        return [
            Section(
                content=TextBlock(text=text),
                source=filename,
                metadata={"format": "text"},
            )
        ]
