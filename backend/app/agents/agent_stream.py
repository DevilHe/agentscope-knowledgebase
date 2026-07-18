"""LangGraph ReAct 事件流 → 前端 SSE（token / cot / tool）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.agents.agent_factory import create_chat_agent
from app.agents.cot_builder import CotBuilder
from app.agents.governance import max_tool_rounds
from app.db.models import User
from app.services.llm import resolve_model_name

TOOL_LABELS: dict[str, str] = {
    "search_knowledge_base": "检索知识库",
    "web_search": "联网搜索",
    "get_weather": "查询天气",
}


def _tool_label(name: str) -> str:
    return TOOL_LABELS.get(name, name)


def _tool_args_json(args: Any) -> str:
    if isinstance(args, str):
        return args
    try:
        return json.dumps(args or {}, ensure_ascii=False)
    except (TypeError, ValueError):
        return "{}"


def _chunk_text(chunk: AIMessageChunk | AIMessage) -> str:
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return ""


async def stream_agent_events(
    question: str,
    history: list,
    user_role: str,
    top_k: int,
    sources_out: list[dict],
    user: User | None = None,
    *,
    model_name: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """ReAct 图流式事件：Plan-and-Execute CoT + token + tool。"""
    graph, prompt_version, system_prompt = create_chat_agent(
        user_role=user_role,
        top_k=top_k,
        sources_out=sources_out,
        user=user,
        model_name=model_name,
    )
    limit = max_tool_rounds()
    resolved_model = model_name or resolve_model_name("chat")
    cot = CotBuilder(question)
    tool_call_count = 0
    # tool_call_id → name / args
    tool_names: dict[str, str] = {}
    tool_inputs: dict[str, str] = {}
    pending_starts: set[str] = set()
    saw_token = False
    generate_started = False

    yield {
        "type": "meta",
        "prompt_version": prompt_version,
        "model": resolved_model,
        "max_tool_rounds": limit,
    }

    for step in cot.initial_steps():
        yield {"type": "cot", "action": "add", "step": step}

    messages = [
        SystemMessage(content=system_prompt),
        *list(history),
        HumanMessage(content=question),
    ]
    # recursion_limit：每轮 agent+tools 约 2 步
    config = {"recursion_limit": max(limit * 2 + 4, 16)}

    try:
        async for event in graph.astream_events(
            {"messages": messages},
            config=config,
            version="v2",
        ):
            kind = event.get("event")
            name = event.get("name") or ""
            data = event.get("data") or {}

            if kind == "on_chat_model_stream":
                chunk = data.get("chunk")
                if not isinstance(chunk, AIMessageChunk):
                    continue
                # 工具调用参数流：不输出为 token
                if chunk.tool_call_chunks:
                    for tc in chunk.tool_call_chunks:
                        tc_id = tc.get("id") or ""
                        tc_name = tc.get("name")
                        if tc_id and tc_name:
                            tool_names[tc_id] = tc_name
                        if tc_id and tc.get("args"):
                            tool_inputs[tc_id] = tool_inputs.get(tc_id, "") + str(
                                tc.get("args") or ""
                            )
                    continue
                delta = _chunk_text(chunk)
                if not delta:
                    continue
                saw_token = True
                if not generate_started and not pending_starts:
                    if not cot.tool_used and not cot.plan_emitted:
                        yield {"type": "cot", "action": "update", "step": cot.analyze_done()}
                        plan = cot.ensure_plan(None)
                        if plan:
                            action, step = plan
                            yield {"type": "cot", "action": action, "step": step}
                            yield {"type": "cot", "action": "update", "step": cot.plan_done()}
                    if cot.tool_used or cot.plan_emitted:
                        for gen_event in cot.maybe_start_generate():
                            yield gen_event
                        generate_started = cot.generate_emitted
                yield {"type": "token", "delta": delta}

            elif kind == "on_chat_model_end":
                output = data.get("output")
                if not isinstance(output, AIMessage):
                    continue
                for tc in output.tool_calls or []:
                    tc_id = str(tc.get("id") or "")
                    tc_name = str(tc.get("name") or "")
                    if not tc_id:
                        continue
                    tool_names[tc_id] = tc_name
                    tool_inputs[tc_id] = _tool_args_json(tc.get("args"))

            elif kind == "on_tool_start":
                # LangChain ToolNode 事件：name=工具名，run_id 作 tool_call_id 兜底
                tool_name = name
                run_id = str(event.get("run_id") or "")
                inputs = data.get("input")
                raw_input = _tool_args_json(inputs) if inputs is not None else "{}"
                # 尽量用真实 tool_call_id
                tool_call_id = run_id
                for tid, tname in tool_names.items():
                    if tname == tool_name and tid not in pending_starts:
                        tool_call_id = tid
                        if tid in tool_inputs:
                            raw_input = tool_inputs[tid]
                        break
                tool_names[tool_call_id] = tool_name
                tool_inputs[tool_call_id] = raw_input
                pending_starts.add(tool_call_id)

                for retract_event in cot.retract_generate():
                    yield retract_event
                generate_started = False
                cot.tool_used = True

                plan = cot.ensure_plan(tool_name)
                if plan:
                    action, step = plan
                    yield {"type": "cot", "action": "update", "step": cot.analyze_done()}
                    yield {"type": "cot", "action": action, "step": step}
                    yield {"type": "cot", "action": "update", "step": cot.plan_done()}

                yield {
                    "type": "cot",
                    "action": "add",
                    "step": cot.execute_start(tool_name, tool_call_id, raw_input),
                }
                yield {
                    "type": "tool",
                    "phase": "start",
                    "tool": tool_name,
                    "label": _tool_label(tool_name),
                    "tool_call_id": tool_call_id,
                }

            elif kind == "on_tool_end":
                tool_name = name
                run_id = str(event.get("run_id") or "")
                tool_call_id = run_id
                for tid in list(pending_starts):
                    if tool_names.get(tid) == tool_name:
                        tool_call_id = tid
                        break
                pending_starts.discard(tool_call_id)
                tool_call_count += 1
                raw_input = tool_inputs.get(tool_call_id, "{}")
                output = data.get("output")
                status = "success"
                if isinstance(output, ToolMessage):
                    content = str(output.content or "")
                    if content.startswith(("未", "搜索", "天气查询失败", "联网搜索失败")):
                        # 部分失败文案仍视为业务结果
                        lower = content.lower()
                        if "失败" in content or "error" in lower or "无法" in content:
                            try:
                                parsed = json.loads(content)
                                if isinstance(parsed, dict) and parsed.get("error"):
                                    status = "error"
                            except json.JSONDecodeError:
                                if "失败" in content or "无法" in content:
                                    status = "error"
                elif isinstance(output, str) and (
                    "失败" in output or output.startswith("未配置")
                ):
                    status = "error"

                yield {
                    "type": "cot",
                    "action": "update",
                    "step": cot.execute_end(
                        tool_name, tool_call_id, raw_input, status
                    ),
                }
                yield {
                    "type": "tool",
                    "phase": "end",
                    "tool": tool_name,
                    "label": _tool_label(tool_name),
                    "tool_call_id": tool_call_id,
                    "status": status,
                }

                if not pending_starts and not cot.generate_emitted:
                    for gen_event in cot.maybe_start_generate():
                        yield gen_event
                    generate_started = cot.generate_emitted

                if tool_call_count >= limit:
                    if cot.generate_emitted:
                        yield {"type": "cot", "action": "update", "step": cot.generate_done()}
                    finish = cot.finish_payload()
                    if finish:
                        yield {"type": "cot", "action": "finish", **finish}
                    yield {
                        "type": "error",
                        "message": f"工具调用已达上限（{limit} 次），请简化问题后重试",
                    }
                    return

    except Exception as exc:
        if cot.generate_emitted:
            yield {"type": "cot", "action": "update", "step": cot.generate_done()}
        finish = cot.finish_payload()
        if finish:
            yield {"type": "cot", "action": "finish", **finish}
        yield {"type": "error", "message": f"Agent 执行失败：{exc}"}
        return

    # 无工具直接回答收尾
    if saw_token and not cot.tool_used:
        if not cot.plan_emitted:
            yield {"type": "cot", "action": "update", "step": cot.analyze_done()}
            plan = cot.ensure_plan(None)
            if plan:
                action, step = plan
                yield {"type": "cot", "action": action, "step": step}
                yield {"type": "cot", "action": "update", "step": cot.plan_done()}
        if not cot.generate_emitted:
            for gen_event in cot.maybe_start_generate():
                yield gen_event

    if cot.generate_emitted:
        yield {"type": "cot", "action": "update", "step": cot.generate_done()}
    finish = cot.finish_payload()
    if finish:
        yield {"type": "cot", "action": "finish", **finish}


async def stream_agent_text(
    question: str,
    history: list,
    user_role: str,
    top_k: int,
    sources_out: list[dict],
) -> AsyncIterator[str]:
    """兼容旧接口：仅输出文本 token。"""
    async for event in stream_agent_events(
        question, history, user_role, top_k, sources_out
    ):
        if event.get("type") == "token":
            yield event["delta"]
