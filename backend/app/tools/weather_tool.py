"""OpenWeather 工具 — AgentScope ToolBase 实现，权限交由 PermissionEngine 裁决。"""

import json
from typing import Any

from agentscope.message import TextBlock, ToolResultState
from agentscope.permission import (
    PermissionBehavior,
    PermissionContext,
    PermissionDecision,
)
from agentscope.tool import ToolBase, ToolChunk

from app.audit.tool_runtime import audit_tool_success, consume_tool_call, guard_tool_call
from app.tools.weather import get_weather


def _is_error_payload(result: str) -> str | None:
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data.get("error"):
        return str(data["error"])
    return None


class WeatherTool(ToolBase):
    """查询城市即时天气（OpenWeather API）。"""

    name: str = "get_weather"
    description: str = "查询某个城市的即时天气情况。city 使用英文城市名，如 Beijing、Shanghai。"
    input_schema: dict = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市英文名，如 Beijing、Shanghai",
            },
        },
        "required": ["city"],
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
        """将决策交给 PermissionEngine（deny/ask/allow 规则链）。"""
        return PermissionDecision(
            behavior=PermissionBehavior.PASSTHROUGH,
            message="Weather tool defers to PermissionEngine.",
        )

    async def __call__(self, city: str) -> ToolChunk:
        payload = {"city": city}
        blocked = guard_tool_call("get_weather", payload)
        if blocked:
            return ToolChunk(
                content=[TextBlock(text=blocked)],
                state=ToolResultState.ERROR,
                is_last=True,
            )
        try:
            consume_tool_call("get_weather")
            result = get_weather(city)
            err = _is_error_payload(result)
            if err:
                return ToolChunk(
                    content=[TextBlock(text=err)],
                    state=ToolResultState.ERROR,
                    is_last=True,
                )
            audit_tool_success("get_weather", payload)
            return ToolChunk(
                content=[TextBlock(text=result)],
                state=ToolResultState.SUCCESS,
                is_last=True,
            )
        except Exception as exc:
            return ToolChunk(
                content=[TextBlock(text=f"天气查询失败：{exc}")],
                state=ToolResultState.ERROR,
                is_last=True,
            )
