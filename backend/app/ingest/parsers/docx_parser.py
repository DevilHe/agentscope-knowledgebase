# -*- coding: utf-8 -*-
"""Word (.docx) parser for RAG ingest."""

import io
from pathlib import Path

from app.ingest.models import Section, TextBlock


class DocxParser:
    supported_media_types = [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]

    @classmethod
    def supported_extensions(cls) -> list[str]:
        return [".docx"]

    async def parse(self, file: bytes | str, filename: str) -> list[Section]:
        if isinstance(file, str):
            data = Path(file).read_bytes()
        else:
            data = file

        try:
            from docx import Document
        except ImportError as exc:
            raise ImportError("请安装 python-docx: pip install python-docx") from exc

        doc = Document(io.BytesIO(data))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        return [
            Section(
                content=TextBlock(text=text),
                source=filename,
                metadata={"format": "docx"},
            )
        ]
