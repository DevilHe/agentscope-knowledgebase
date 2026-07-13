# -*- coding: utf-8 -*-
"""分块策略：对外仅暴露 CHUNK_TOKEN_SIZE 等少量配置，目标区间 512–1024 token。"""

from app.config import settings

# 在满足语义边界等条件下，单块尽量落在此区间
TARGET_CHUNK_MIN_TOKENS = 512
EMBED_BATCH_SIZE = 32


def chunk_max_tokens() -> int:
    return settings.chunk_token_size


def chunk_min_tokens() -> int:
    """合并下限：不超过 max，且不低于 TARGET_CHUNK_MIN。"""
    return min(TARGET_CHUNK_MIN_TOKENS, settings.chunk_token_size)


def chunk_min_unit_tokens() -> int:
    """过短语义单元（如列表项 f）与相邻句合并的阈值。"""
    return max(32, chunk_min_tokens() // 10)


def chunk_min_retrieval_tokens() -> int:
    """检索时跳过明显过短片段（约为合并下限的 1/8）。"""
    return max(64, chunk_min_tokens() // 8)
