import json
import time
import uuid
from typing import Any

from app.config import settings
from app.db.redis_client import get_redis

BLACKLIST_PREFIX = "auth:blacklist:"
REFRESH_PREFIX = "auth:refresh:"
RATE_PREFIX = "auth:rate:"
SESSION_PREFIX = "auth:session:"


def _ttl_until(exp_ts: float) -> int:
    return max(1, int(exp_ts - time.time()))


def blacklist_jti(jti: str, exp_ts: float) -> None:
    get_redis().setex(f"{BLACKLIST_PREFIX}{jti}", _ttl_until(exp_ts), "1")


def is_jti_blacklisted(jti: str) -> bool:
    return bool(get_redis().exists(f"{BLACKLIST_PREFIX}{jti}"))


def store_refresh_token(token: str, payload: dict[str, Any]) -> None:
    ttl = settings.jwt_refresh_expire_days * 86400
    get_redis().setex(
        f"{REFRESH_PREFIX}{token}", ttl, json.dumps(payload, ensure_ascii=False)
    )


def get_refresh_token(token: str) -> dict[str, Any] | None:
    raw = get_redis().get(f"{REFRESH_PREFIX}{token}")
    if not raw:
        return None
    return json.loads(raw)


def revoke_refresh_token(token: str) -> None:
    get_redis().delete(f"{REFRESH_PREFIX}{token}")


def revoke_all_refresh_tokens_for_user(user_id: str) -> None:
    client = get_redis()
    for key in client.scan_iter(f"{REFRESH_PREFIX}*"):
        raw = client.get(key)
        if not raw:
            continue
        data = json.loads(raw)
        if data.get("sub") == user_id:
            client.delete(key)


def _session_ttl_seconds() -> int:
    return max(1, settings.jwt_refresh_expire_days) * 86400


def start_user_session(user_id: str) -> str:
    """创建或替换用户当前活跃会话（单设备登录）。"""
    session_id = str(uuid.uuid4())
    get_redis().setex(f"{SESSION_PREFIX}{user_id}", _session_ttl_seconds(), session_id)
    return session_id


def get_user_session_id(user_id: str) -> str | None:
    raw = get_redis().get(f"{SESSION_PREFIX}{user_id}")
    if not raw:
        return None
    return raw.decode() if isinstance(raw, bytes) else raw


def clear_user_session(user_id: str) -> None:
    get_redis().delete(f"{SESSION_PREFIX}{user_id}")


def validate_user_session(user_id: str, session_id: str | None) -> tuple[bool, str | None]:
    if not session_id:
        return False, "会话已失效，请重新登录"
    active_sid = get_user_session_id(user_id)
    if not active_sid:
        return False, "会话已过期，请重新登录"
    if active_sid != session_id:
        return False, "账号已在其他设备登录，请重新登录"
    return True, None


def invalidate_user_sessions(user_id: str) -> None:
    revoke_all_refresh_tokens_for_user(user_id)
    clear_user_session(user_id)


def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """返回 True 表示未超限，False 表示已超限。"""
    redis_key = f"{RATE_PREFIX}{key}"
    client = get_redis()
    count = client.incr(redis_key)
    if count == 1:
        client.expire(redis_key, window_seconds)
    return count <= limit
