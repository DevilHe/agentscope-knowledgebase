# -*- coding: utf-8 -*-
"""文档解析/分块用的轻量数据结构（替代 AgentScope Section/Chunk）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextBlock:
    text: str


@dataclass
class Section:
    content: TextBlock | Any
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    content: TextBlock | Any
    source: str = ""
    chunk_index: int = 0
    total_chunks: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
