import json

import redis

from app.config import settings

_client: redis.Redis | None = None
TASK_TTL = 86400


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def set_task_status(task_id: str, payload: dict) -> None:
    get_redis().setex(f"ingest:task:{task_id}", TASK_TTL, json.dumps(payload, ensure_ascii=False))


def get_task_status(task_id: str) -> dict | None:
    raw = get_redis().get(f"ingest:task:{task_id}")
    if not raw:
        return None
    return json.loads(raw)
