"""工具角色白名单（替代 AgentScope PermissionEngine）。"""

ROLE_TOOL_ALLOWLIST: dict[str, frozenset[str]] = {
    "admin": frozenset({"get_weather", "search_knowledge_base", "web_search"}),
    "user": frozenset({"get_weather", "search_knowledge_base", "web_search"}),
}


def is_tool_allowed_for_role(tool_name: str, user_role: str) -> bool:
    return tool_name in ROLE_TOOL_ALLOWLIST.get(user_role, frozenset())
