"""LangGraph ReAct Agent 工厂（方案 A：条件边 tools_condition）。"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.core.prompt_registry import resolve_system_prompt
from app.db.models import User
from app.services.llm import get_chat_model, resolve_model_name
from app.tools.langchain_tools import create_agent_tools


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def create_chat_agent(
    user_role: str,
    top_k: int,
    sources_out: list[dict],
    user: User | None = None,
    *,
    model_name: str | None = None,
):
    """创建按需检索 ReAct 图；返回 (compiled_graph, prompt_version, system_prompt)。"""
    system_prompt, prompt_version = resolve_system_prompt(user.id if user else None)
    tools = create_agent_tools(
        top_k=top_k,
        sources_out=sources_out,
        user=user,
        user_role=user_role,
    )
    resolved_model = model_name or resolve_model_name("chat")
    model = get_chat_model(stream=True, model_name=resolved_model)
    model_with_tools = model.bind_tools(tools) if tools else model

    async def agent_node(state: AgentState) -> dict:
        response = await model_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    if tools:
        graph.add_node("tools", ToolNode(tools))
        graph.add_edge(START, "agent")
        # 方案 A：有 tool_calls → tools，否则 END（按需检索）
        graph.add_conditional_edges("agent", tools_condition)
        graph.add_edge("tools", "agent")
    else:
        graph.add_edge(START, "agent")
        graph.add_edge("agent", END)

    return graph.compile(), prompt_version, system_prompt
