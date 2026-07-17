# -*- coding: utf-8 -*-
"""PDF 解析（pypdf）。"""

from __future__ import annotations

from pathlib import Path

from app.ingest.models import Section, TextBlock


class PDFParser:
    async def parse(self, file: bytes | str, filename: str) -> list[Section]:
        if isinstance(file, str):
            data = Path(file).read_bytes()
        else:
            data = file

        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ImportError("请安装 pypdf: pip install pypdf") from exc

        import io

        reader = PdfReader(io.BytesIO(data))
        sections: list[Section] = []
        for page_idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            sections.append(
                Section(
                    content=TextBlock(text=text),
                    source=filename,
                    metadata={"format": "pdf", "page": page_idx},
                )
            )
        if not sections:
            # 整份文档无文本时仍返回空列表，由 pipeline 报错
            return []
        return sections
