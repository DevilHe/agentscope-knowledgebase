# -*- coding: utf-8 -*-
"""UTC 时间序列化（数据库存 naive UTC，API 返回带 Z 的 ISO）。"""

from datetime import datetime


def to_utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(datetime.UTC).replace(tzinfo=None).isoformat() + "Z"
    return value.isoformat() + "Z"
