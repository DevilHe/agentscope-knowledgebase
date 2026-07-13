import json

import httpx

from app.config import settings


def get_weather(city: str) -> str:
    """查询指定城市的即时天气。

    Args:
        city: 城市英文名，如 Beijing、Shanghai。

    Returns:
        OpenWeather API 返回的天气信息（JSON 字符串）。
    """
    if not settings.openweather_api_key or not settings.openweather_api_url:
        return json.dumps({"error": "未配置 OPENWEATHER_API_KEY 或 OPENWEATHER_API_URL"}, ensure_ascii=False)

    params = {
        "q": city,
        "appid": settings.openweather_api_key,
        "units": "metric",
        "lang": "zh_cn",
    }
    response = httpx.get(settings.openweather_api_url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    return json.dumps(data, ensure_ascii=False)
