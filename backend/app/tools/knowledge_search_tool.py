"""知识库检索工具 — 供 Agent 按需调用 RAG。"""

import json
from typing import Any

from agentscope.message import TextBlock, ToolResultState
from agentscope.permission import (
    PermissionBehavior,
    PermissionContext,
    PermissionDecision,
)
from agentscope.tool import ToolBase, ToolChunk

from app.audit.tool_runtime import audit_tool_success, guard_tool_call
from app.db.models import User
from app.services.retrieval import retrieve_sources_for_user


def create_knowledge_search_tool(
    top_k: int,
    sources_out: list[dict],
    user: User | None = None,
) -> ToolBase:
    """创建绑定用户权限与引用收集器的检索工具实例。"""

    class KnowledgeSearchTool(ToolBase):
        name: str = "search_knowledge_base"
        description: str = (
            "从已入库的知识库文档中检索与问题相关的段落。"
            "当用户询问文档、规范、技术约定、代码风格等内容时使用；"
            "返回检索到的原文片段，请据此回答，不要编造。"
        )
        input_schema: dict = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用于检索的用户问题或关键词",
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
                message="Knowledge search defers to PermissionEngine.",
            )

        async def __call__(self, query: str) -> ToolChunk:
            payload = {"query": query}
            blocked = guard_tool_call("search_knowledge_base", payload)
            if blocked:
                return ToolChunk(
                    content=[TextBlock(text=blocked)],
                    state=ToolResultState.ERROR,
                    is_last=True,
                )
            if user is None:
                return ToolChunk(
                    content=[TextBlock(text="未登录，无法检索知识库")],
                    state=ToolResultState.ERROR,
                    is_last=True,
                )

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
            payload_data = {
                "found": bool(sources),
                "chunk_count": len(sources),
                "context": context if context else "未找到相关知识库内容",
            }
            return ToolChunk(
                content=[TextBlock(text=json.dumps(payload_data, ensure_ascii=False))],
                state=ToolResultState.SUCCESS,
                is_last=True,
            )

    return KnowledgeSearchTool()
