"""LangChain 工具：知识库检索 / 联网搜索 / 多城天气。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator

from app.agents.permissions import is_tool_allowed_for_role
from app.audit.tool_runtime import audit_tool_success, consume_tool_call, guard_tool_call
from app.db.models import User
from app.services.retrieval import retrieve_sources_for_user
from app.tools.search import web_search as tavily_web_search
from app.tools.weather import get_weather as fetch_weather


class KnowledgeSearchInput(BaseModel):
    query: str = Field(description="用于检索的用户问题或关键词")


class WebSearchInput(BaseModel):
    query: str = Field(description="搜索关键词或问题")
    max_results: int = Field(default=3, description="返回结果数量，默认 3")


class WeatherInput(BaseModel):
    cities: list[str] = Field(
        description=(
            "英文城市名列表，如 [\"Beijing\", \"Shanghai\"]。"
            "多城市一次传入，不要多次调用本工具。"
        )
    )

    @field_validator("cities", mode="before")
    @classmethod
    def _coerce_cities(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, (list, tuple)):
            return [str(v).strip() for v in value if str(v).strip()]
        return []


_WEB_ERROR_PREFIXES = (
    "未配置 TAVILY_API_KEY",
    "搜索超时",
    "搜索网络错误",
)


def create_agent_tools(
    *,
    top_k: int,
    sources_out: list[dict],
    user: User | None,
    user_role: str,
) -> list[StructuredTool]:
    """按角色白名单组装 LangChain 工具。"""

    async def search_knowledge_base(query: str) -> str:
        payload = {"query": query}
        blocked = guard_tool_call("search_knowledge_base", payload)
        if blocked:
            return blocked
        if user is None:
            return "未登录，无法检索知识库"

        from app.db.models import SessionLocal

        db = SessionLocal()
        try:
            context, sources = await retrieve_sources_for_user(
                query,
                top_k,
                user=user,
                db=db,
            )
        finally:
            db.close()
        sources_out.extend(sources)
        audit_tool_success(
            "search_knowledge_base", {**payload, "found": bool(sources)}
        )
        return json.dumps(
            {
                "found": bool(sources),
                "chunk_count": len(sources),
                "context": context if context else "未找到相关知识库内容",
            },
            ensure_ascii=False,
        )

    def web_search(query: str, max_results: int = 3) -> str:
        payload = {"query": query, "max_results": max_results}
        blocked = guard_tool_call("web_search", payload)
        if blocked:
            return blocked
        try:
            consume_tool_call("web_search")
            result = tavily_web_search(query, max_results=max_results)
            if any(result.startswith(p) for p in _WEB_ERROR_PREFIXES):
                return result
            audit_tool_success("web_search", payload)
            return result
        except Exception as exc:
            return f"联网搜索失败：{exc}"

    def get_weather(cities: list[str]) -> str:
        payload: dict[str, Any] = {"cities": cities}
        blocked = guard_tool_call("get_weather", payload)
        if blocked:
            return blocked
        try:
            consume_tool_call("get_weather")
            result = fetch_weather(cities)
            try:
                data = json.loads(result)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict) and data.get("error"):
                return result
            audit_tool_success("get_weather", payload)
            return result
        except Exception as exc:
            return f"天气查询失败：{exc}"

    candidates = [
        StructuredTool.from_function(
            coroutine=search_knowledge_base,
            name="search_knowledge_base",
            description=(
                "从已入库的知识库文档中检索与问题相关的段落。"
                "当用户询问文档、规范、技术约定、代码风格等内容时使用；"
                "打招呼、闲聊、身份介绍时不要调用。"
                "返回检索到的原文片段，请据此回答，不要编造。"
            ),
            args_schema=KnowledgeSearchInput,
        ),
        StructuredTool.from_function(
            func=web_search,
            name="web_search",
            description=(
                "搜索互联网上的实时信息。"
                "当用户询问新闻、最新动态、知识库中没有的内容，或需要联网补充信息时使用。"
                "同一问题通常只需调用一次，不要对相同关键词重复搜索。"
            ),
            args_schema=WebSearchInput,
        ),
        StructuredTool.from_function(
            func=get_weather,
            name="get_weather",
            description=(
                "查询一个或多个城市的即时天气。"
                "传入英文城市名列表 cities，如 [\"Beijing\", \"Shanghai\"]；"
                "多城市必须一次传入，禁止多次调用。"
            ),
            args_schema=WeatherInput,
        ),
    ]
    return [t for t in candidates if is_tool_allowed_for_role(t.name, user_role)]
