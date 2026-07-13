# -*- coding: utf-8 -*-
"""Agent 治理：配额、熔断、工具轮次与超时。"""

from __future__ import annotations

from datetime import date

from app.config import settings
from app.db.redis_client import get_redis

_CIRCUIT_FAIL_KEY = "agent:circuit:failures"
_CIRCUIT_OPEN_KEY = "agent:circuit:open"
_TOKEN_QUOTA_PREFIX = "quota:tokens:"


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    ratio = settings.user_token_estimate_chars_per_token
    if ratio <= 0:
        ratio = 2.0
    return max(1, int(len(text) / ratio))


def check_user_token_quota(user_id: str, extra_tokens: int = 0) -> str | None:
    limit = settings.user_token_quota_daily
    if limit <= 0:
        return None
    key = f"{_TOKEN_QUOTA_PREFIX}{user_id}:{date.today().isoformat()}"
    used = int(get_redis().get(key) or 0)
    if used + extra_tokens >= limit:
        return f"今日 Token 用量已达上限（{limit}）"
    return None


def consume_user_tokens(user_id: str, tokens: int) -> None:
    limit = settings.user_token_quota_daily
    if limit <= 0 or tokens <= 0:
        return
    key = f"{_TOKEN_QUOTA_PREFIX}{user_id}:{date.today().isoformat()}"
    client = get_redis()
    count = client.incrby(key, tokens)
    if count == tokens:
        client.expire(key, 86400)


def is_circuit_open() -> bool:
    return bool(get_redis().exists(_CIRCUIT_OPEN_KEY))


def circuit_open_message() -> str:
    return "服务繁忙，请稍后再试（熔断保护中）"


def record_agent_failure() -> None:
    threshold = settings.agent_circuit_breaker_fail_threshold
    if threshold <= 0:
        return
    client = get_redis()
    failures = client.incr(_CIRCUIT_FAIL_KEY)
    if failures == 1:
        client.expire(_CIRCUIT_FAIL_KEY, settings.agent_circuit_breaker_cooldown_seconds)
    if failures >= threshold:
        client.setex(
            _CIRCUIT_OPEN_KEY,
            settings.agent_circuit_breaker_cooldown_seconds,
            "1",
        )
        client.delete(_CIRCUIT_FAIL_KEY)


def record_agent_success() -> None:
    get_redis().delete(_CIRCUIT_FAIL_KEY)


def max_tool_rounds() -> int:
    return max(1, settings.agent_max_tool_rounds)


def reply_timeout_seconds() -> int:
    return max(30, settings.agent_reply_timeout_seconds)
