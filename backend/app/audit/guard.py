import re
from datetime import date

from app.config import settings
from app.db.redis_client import get_redis

_QUOTA_PREFIX = "quota:"


def _sensitive_patterns() -> list[re.Pattern[str]]:
    words = [w.strip() for w in settings.sensitive_words.split(",") if w.strip()]
    return [re.compile(re.escape(word), re.IGNORECASE) for word in words]


def check_sensitive_text(text: str) -> str | None:
    """命中敏感词返回原因，否则返回 None。"""
    if not text or not settings.sensitive_words.strip():
        return None
    for pattern in _sensitive_patterns():
        if pattern.search(text):
            return "内容包含敏感词，已被拦截"
    return None


def _quota_limit(tool_name: str) -> int:
    mapping = {
        "web_search": settings.tool_quota_web_search_daily,
        "get_weather": settings.tool_quota_weather_daily,
        "llm": settings.tool_quota_llm_daily,
    }
    return mapping.get(tool_name, 0)


def check_tool_quota(user_id: str, tool_name: str) -> str | None:
    """未超限返回 None，超限返回提示。"""
    limit = _quota_limit(tool_name)
    if limit <= 0:
        return None
    key = f"{_QUOTA_PREFIX}{user_id}:{tool_name}:{date.today().isoformat()}"
    client = get_redis()
    count = int(client.get(key) or 0)
    if count >= limit:
        return f"{tool_name} 今日调用次数已达上限（{limit} 次）"
    return None


def consume_tool_quota(user_id: str, tool_name: str) -> None:
    limit = _quota_limit(tool_name)
    if limit <= 0:
        return
    key = f"{_QUOTA_PREFIX}{user_id}:{tool_name}:{date.today().isoformat()}"
    client = get_redis()
    count = client.incr(key)
    if count == 1:
        client.expire(key, 86400)
