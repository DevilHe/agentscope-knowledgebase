# -*- coding: utf-8 -*-
"""中文友好的稀疏向量（字符/二元组 + 英文词哈希），供 Qdrant sparse 检索。"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from qdrant_client.http import models as qmodels

_WORD_RE = re.compile(r"[a-z0-9_]+", re.I)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    tokens: list[str] = _WORD_RE.findall(text)
    chars = _CJK_RE.findall(text)
    tokens.extend(chars)
    if len(chars) >= 2:
        tokens.extend(a + b for a, b in zip(chars, chars[1:]))
    return tokens


def _hash_token(token: str) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % (2**31 - 1)


def text_to_sparse(text: str, *, max_terms: int = 256) -> qmodels.SparseVector:
    counts = Counter(tokenize(text))
    if not counts:
        return qmodels.SparseVector(indices=[0], values=[1.0])

    merged: dict[int, float] = {}
    for term, tf in counts.most_common(max_terms):
        idx = _hash_token(term)
        weight = 1.0 + math.log(float(tf))
        merged[idx] = merged.get(idx, 0.0) + weight

    indices = sorted(merged.keys())
    values = [merged[i] for i in indices]
    return qmodels.SparseVector(indices=indices, values=values)
