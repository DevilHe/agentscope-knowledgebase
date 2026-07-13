"""AgentScope 工具权限：PermissionContext + PermissionEngine + 角色白名单。"""

from agentscope.permission import (
    PermissionBehavior,
    PermissionContext,
    PermissionEngine,
    PermissionMode,
    PermissionRule,
)

# 角色 → 允许自动执行的工具（经 PermissionEngine allow 规则注入）
ROLE_TOOL_ALLOWLIST: dict[str, frozenset[str]] = {
    "admin": frozenset({"get_weather", "search_knowledge_base", "web_search"}),
    "user": frozenset({"get_weather", "search_knowledge_base", "web_search"}),
}


def build_permission_context(user_role: str) -> PermissionContext:
    """按用户角色构建 PermissionContext，并通过 PermissionEngine 写入 allow 规则。"""
    context = PermissionContext(mode=PermissionMode.DEFAULT)
    engine = PermissionEngine(context)
    for tool_name in ROLE_TOOL_ALLOWLIST.get(user_role, frozenset()):
        engine.add_rule(
            PermissionRule(
                tool_name=tool_name,
                rule_content=None,
                behavior=PermissionBehavior.ALLOW,
                source=f"role:{user_role}",
            ),
        )
    return context


def is_tool_allowed_for_role(tool_name: str, user_role: str) -> bool:
    return tool_name in ROLE_TOOL_ALLOWLIST.get(user_role, frozenset())
