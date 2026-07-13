"""Tavily 联网搜索工具 — AgentScope ToolBase 实现。"""

from typing import Any

from agentscope.message import TextBlock, ToolResultState
from agentscope.permission import (
    PermissionBehavior,
    PermissionContext,
    PermissionDecision,
)
from agentscope.tool import ToolBase, ToolChunk

from app.audit.tool_runtime import audit_tool_success, consume_tool_call, guard_tool_call
from app.tools.search import web_search

_ERROR_PREFIXES = (
    "未配置 TAVILY_API_KEY",
    "搜索超时",
    "搜索网络错误",
)


class WebSearchTool(ToolBase):
    """通过 Tavily 搜索互联网上的实时信息。"""

    name: str = "web_search"
    description: str = (
        "搜索互联网上的实时信息。"
        "当用户询问新闻、最新动态、知识库中没有的内容，或需要联网补充信息时使用。"
        "同一问题通常只需调用一次，不要对相同关键词重复搜索。"
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词或问题",
            },
            "max_results": {
                "type": "integer",
                "description": "返回结果数量，默认 3",
                "default": 3,
            },
        },
        "required": ["query"],
    }
    is_concurrency_safe: bool = True
    is_read_only: bool = True
    is_external_tool: bool = False
    is_mcp: bool = False

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.PASSTHROUGH,
            message="Web search defers to PermissionEngine.",
        )

    async def __call__(self, query: str, max_results: int = 3) -> ToolChunk:
        payload = {"query": query, "max_results": max_results}
        blocked = guard_tool_call("web_search", payload)
        if blocked:
            return ToolChunk(
                content=[TextBlock(text=blocked)],
                state=ToolResultState.ERROR,
                is_last=True,
            )
        try:
            consume_tool_call("web_search")
            result = web_search(query, max_results=max_results)
            if any(result.startswith(p) for p in _ERROR_PREFIXES):
                return ToolChunk(
                    content=[TextBlock(text=result)],
                    state=ToolResultState.ERROR,
                    is_last=True,
                )
            audit_tool_success("web_search", payload)
            return ToolChunk(
                content=[TextBlock(text=result)],
                state=ToolResultState.SUCCESS,
                is_last=True,
            )
        except Exception as exc:
            return ToolChunk(
                content=[TextBlock(text=f"联网搜索失败：{exc}")],
                state=ToolResultState.ERROR,
                is_last=True,
            )
