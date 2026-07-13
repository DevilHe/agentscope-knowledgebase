import json
from collections.abc import AsyncIterator
from typing import Any

from agentscope.event import (
    ConfirmResult,
    RequireUserConfirmEvent,
    TextBlockDeltaEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
    UserConfirmResultEvent,
)
from agentscope.message import Msg, UserMsg
from agentscope.permission import PermissionBehavior, PermissionEngine

from app.agents.agent_factory import create_chat_agent
from app.agents.cot_builder import CotBuilder
from app.agents.governance import max_tool_rounds
from app.agents.permissions import is_tool_allowed_for_role
from app.db.models import User
from app.services.llm import resolve_model_name

TOOL_LABELS: dict[str, str] = {
    "search_knowledge_base": "检索知识库",
    "web_search": "联网搜索",
    "get_weather": "查询天气",
}


async def _resolve_tool_input(raw_input: str) -> dict:
    try:
        data = json.loads(raw_input or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _tool_label(name: str) -> str:
    return TOOL_LABELS.get(name, name)


async def _build_confirm_event(
    agent,
    event: RequireUserConfirmEvent,
    user_role: str,
) -> UserConfirmResultEvent:
    """对 RequireUserConfirmEvent 做服务端裁决（PermissionEngine + 角色白名单）。"""
    engine = PermissionEngine(agent.state.permission_context)
    confirm_results: list[ConfirmResult] = []

    for tool_call in event.tool_calls:
        tool = await agent.toolkit.get_tool(tool_call.name)
        parsed_input = await _resolve_tool_input(tool_call.input)
        if tool is None or not is_tool_allowed_for_role(tool_call.name, user_role):
            confirm_results.append(
                ConfirmResult(confirmed=False, tool_call=tool_call),
            )
            continue

        decision = await engine.check_permission(tool, parsed_input)
        confirm_results.append(
            ConfirmResult(
                confirmed=decision.behavior == PermissionBehavior.ALLOW,
                tool_call=tool_call,
            ),
        )

    return UserConfirmResultEvent(
        reply_id=event.reply_id,
        confirm_results=confirm_results,
    )


def _finish_reply_round(
    cot: CotBuilder,
    *,
    saw_token: bool,
    pending_tool_calls: int,
) -> list[dict[str, Any]]:
    """一轮 reply_stream 结束后补发规划/生成步骤，保证顺序正确。"""
    events: list[dict[str, Any]] = []
    if not saw_token or pending_tool_calls > 0:
        return events

    if not cot.tool_used:
        events.append({"type": "cot", "action": "update", "step": cot.analyze_done()})
        plan = cot.ensure_plan(None)
        if plan:
            action, step = plan
            events.append({"type": "cot", "action": action, "step": step})
            events.append({"type": "cot", "action": "update", "step": cot.plan_done()})
        events.extend(cot.maybe_start_generate())
        return events

    if cot.tool_used and not cot.generate_emitted:
        events.extend(cot.maybe_start_generate())
    return events


async def stream_agent_events(
    question: str,
    history: list[Msg],
    user_role: str,
    top_k: int,
    sources_out: list[dict],
    user: User | None = None,
    *,
    model_name: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Agent.reply_stream 事件流：Plan-and-Execute CoT + token + tool。"""
    agent, prompt_version = create_chat_agent(
        history,
        user_role=user_role,
        top_k=top_k,
        sources_out=sources_out,
        user=user,
        model_name=model_name,
    )
    pending: Msg | UserConfirmResultEvent = UserMsg(name="user", content=question)
    tool_names: dict[str, str] = {}
    tool_call_count = 0
    limit = max_tool_rounds()
    resolved_model = model_name or resolve_model_name("chat")
    cot = CotBuilder(question)
    tool_inputs: dict[str, str] = {}

    yield {
        "type": "meta",
        "prompt_version": prompt_version,
        "model": resolved_model,
        "max_tool_rounds": limit,
    }

    for step in cot.initial_steps():
        yield {"type": "cot", "action": "add", "step": step}

    while True:
        confirm_event: RequireUserConfirmEvent | None = None
        pending_tool_calls = 0
        saw_token = False

        async for event in agent.reply_stream(inputs=pending):
            if isinstance(event, TextBlockDeltaEvent) and event.delta:
                saw_token = True
                if pending_tool_calls == 0 and not cot.generate_emitted:
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
                yield {"type": "token", "delta": event.delta}
            elif isinstance(event, ToolCallStartEvent):
                for retract_event in cot.retract_generate():
                    yield retract_event
                cot.tool_used = True
                pending_tool_calls += 1

                tool_name = event.tool_call_name
                tool_names[event.tool_call_id] = tool_name
                tool_inputs.setdefault(event.tool_call_id, "")

                plan = cot.ensure_plan(tool_name)
                if plan:
                    action, step = plan
                    yield {"type": "cot", "action": "update", "step": cot.analyze_done()}
                    yield {"type": "cot", "action": action, "step": step}
                    yield {"type": "cot", "action": "update", "step": cot.plan_done()}

                yield {
                    "type": "cot",
                    "action": "add",
                    "step": cot.execute_start(
                        tool_name, event.tool_call_id, tool_inputs[event.tool_call_id]
                    ),
                }
                yield {
                    "type": "tool",
                    "phase": "start",
                    "tool": tool_name,
                    "label": _tool_label(tool_name),
                    "tool_call_id": event.tool_call_id,
                }
            elif isinstance(event, ToolCallDeltaEvent):
                tool_inputs[event.tool_call_id] = (
                    tool_inputs.get(event.tool_call_id, "") + (event.delta or "")
                )
            elif isinstance(event, ToolCallEndEvent):
                tool_name = tool_names.get(event.tool_call_id, "tool")
                raw_input = tool_inputs.get(event.tool_call_id, "")
                yield {
                    "type": "cot",
                    "action": "update",
                    "step": cot.execute_update(tool_name, event.tool_call_id, raw_input),
                }
            elif isinstance(event, ToolResultEndEvent):
                pending_tool_calls = max(0, pending_tool_calls - 1)
                tool_call_count += 1
                tool_name = tool_names.get(event.tool_call_id, "tool")
                status = getattr(event.state, "value", str(event.state))
                raw_input = tool_inputs.get(event.tool_call_id, "")
                yield {
                    "type": "cot",
                    "action": "update",
                    "step": cot.execute_end(
                        tool_name, event.tool_call_id, raw_input, status
                    ),
                }
                yield {
                    "type": "tool",
                    "phase": "end",
                    "tool": tool_name,
                    "label": _tool_label(tool_name),
                    "tool_call_id": event.tool_call_id,
                    "status": status,
                }
                if pending_tool_calls == 0 and not cot.generate_emitted:
                    for gen_event in cot.maybe_start_generate():
                        yield gen_event
                if tool_call_count >= limit:
                    yield {
                        "type": "error",
                        "message": f"工具调用已达上限（{limit} 次），请简化问题后重试",
                    }
                    return
            elif isinstance(event, RequireUserConfirmEvent):
                confirm_event = event

        for extra in _finish_reply_round(
            cot, saw_token=saw_token, pending_tool_calls=pending_tool_calls
        ):
            yield extra

        if confirm_event is None:
            break

        pending = await _build_confirm_event(agent, confirm_event, user_role)

    if cot.generate_emitted:
        yield {"type": "cot", "action": "update", "step": cot.generate_done()}
    # 无生成步骤时（异常中断等）兜底结束思考
    finish = cot.finish_payload()
    if finish:
        yield {"type": "cot", "action": "finish", **finish}


async def stream_agent_text(
    question: str,
    history: list[Msg],
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
