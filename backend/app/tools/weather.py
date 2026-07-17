"""OpenWeather 查询：cities 数组支持单个或多个城市。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from app.config import settings

_MAX_CITIES = 5


def _fetch_one(city: str) -> dict:
    params = {
        "q": city,
        "appid": settings.openweather_api_key,
        "units": "metric",
        "lang": "zh_cn",
    }
    response = httpx.get(settings.openweather_api_url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _normalize_cities(cities: list[str] | str | None) -> list[str]:
    """接受 list 或单个字符串，去空白、去重（保序）。"""
    if cities is None:
        return []
    if isinstance(cities, str):
        raw_list = [cities]
    else:
        raw_list = list(cities)

    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in raw_list:
        name = str(raw or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(name)
    return cleaned


def get_weather(cities: list[str] | str) -> str:
    """查询一个或多个城市的即时天气。

    Args:
        cities: 英文城市名列表，如 ``["Beijing"]`` 或 ``["Beijing", "Shanghai"]``；
            也接受单个字符串 ``"Beijing"``。

    Returns:
        JSON 字符串：``{"cities": {"Beijing": {...}, ...}}``；失败时含 ``error``。
    """
    if not settings.openweather_api_key or not settings.openweather_api_url:
        return json.dumps(
            {"error": "未配置 OPENWEATHER_API_KEY 或 OPENWEATHER_API_URL"},
            ensure_ascii=False,
        )

    cleaned = _normalize_cities(cities)
    if not cleaned:
        return json.dumps({"error": "未提供有效城市名"}, ensure_ascii=False)

    if len(cleaned) > _MAX_CITIES:
        return json.dumps(
            {
                "error": f"一次最多查询 {_MAX_CITIES} 个城市，请减少后重试",
                "cities": cleaned,
            },
            ensure_ascii=False,
        )

    results: dict[str, object] = {}
    workers = min(len(cleaned), _MAX_CITIES)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one, city): city for city in cleaned}
        for fut in as_completed(futures):
            city = futures[fut]
            try:
                results[city] = fut.result()
            except Exception as exc:
                results[city] = {"error": str(exc)}

    return json.dumps({"cities": results}, ensure_ascii=False)
