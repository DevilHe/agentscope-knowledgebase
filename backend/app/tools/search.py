import httpx

from app.config import settings

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def web_search(query: str, max_results: int = 3) -> str:
    """使用 Tavily 搜索互联网内容。"""
    if not settings.tavily_api_key:
        return "未配置 TAVILY_API_KEY，无法执行联网搜索"

    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }

    try:
        response = httpx.post(TAVILY_SEARCH_URL, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("results", []):
            results.append(f"- {item['title']}\n  {item['content']}\n  {item['url']}")

        return "\n".join(results) if results else f"没有找到关于「{query}」的结果"

    except httpx.TimeoutException:
        return "搜索超时，请稍后重试"
    except httpx.HTTPError as e:
        return f"搜索网络错误：{e}"
