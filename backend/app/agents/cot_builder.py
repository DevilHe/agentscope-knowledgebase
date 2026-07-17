# -*- coding: utf-8 -*-
"""Plan-and-Execute 思考过程：先规划，再逐步执行。"""

from __future__ import annotations

import json
import time
from typing import Any


def _truncate(text: str, limit: int = 80) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _parse_tool_input(raw_input: str) -> dict[str, Any]:
    try:
        data = json.loads(raw_input or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _tool_icon(tool: str | None) -> str:
    if not tool:
        return "spark"
    return {
        "search_knowledge_base": "search",
        "web_search": "globe",
        "get_weather": "weather",
    }.get(tool, "tool")


def _plan_text(tool: str | None) -> str:
    if tool == "search_knowledge_base":
        return "计划：检索知识库"
    if tool == "web_search":
        return "计划：联网搜索"
    if tool == "get_weather":
        return "计划：查询天气"
    return "计划：直接生成回答"


def _execute_text(tool: str, raw_input: str = "", *, failed: bool = False) -> str:
    parsed = _parse_tool_input(raw_input)
    if tool == "search_knowledge_base":
        query = _truncate(str(parsed.get("query") or ""))
        base = f"检索知识库{f'：{query}' if query else ''}"
        return f"{base}（失败）" if failed else base
    if tool == "web_search":
        query = _truncate(str(parsed.get("query") or parsed.get("q") or ""))
        if failed:
            return f"调用 web_search 工具联网搜索失败{f'：{query}' if query else ''}"
        return f"调用 web_search 工具联网搜索{f'：{query}' if query else ''}"
    if tool == "get_weather":
        cities = parsed.get("cities")
        if isinstance(cities, list) and cities:
            city_label = "、".join(str(c) for c in cities if c)
        else:
            city_label = str(parsed.get("city") or "").strip()
        if failed:
            return f"调用 get_weather 工具失败{f'（{city_label}）' if city_label else ''}"
        return f"调用 get_weather 工具并返回结果{f'（{city_label}）' if city_label else ''}"
    return "执行工具失败" if failed else "执行工具"


class CotBuilder:
    def __init__(self, question: str) -> None:
        self.question = question
        self.started_at = time.monotonic()
        self.thinking_finished_at: float | None = None
        self.finished = False
        self.plan_tool: str | None = None
        self.plan_emitted = False
        self.generate_emitted = False
        self.tool_used = False

    def initial_steps(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "analyze",
                "phase": "analyze",
                "kind": "analyze",
                "text": f"分析问题：{_truncate(self.question)}",
                "icon": "analyze",
                "status": "running",
            }
        ]

    def analyze_done(self) -> dict[str, Any]:
        return {
            "id": "analyze",
            "phase": "analyze",
            "kind": "analyze",
            "text": f"分析问题：{_truncate(self.question)}",
            "icon": "analyze",
            "status": "done",
        }

    def _build_plan_step(self, tool: str | None) -> dict[str, Any]:
        return {
            "id": "plan",
            "phase": "plan",
            "kind": "plan",
            "text": _plan_text(tool),
            "icon": _tool_icon(tool),
            "status": "running",
        }

    def plan_done(self) -> dict[str, Any]:
        return {
            "id": "plan",
            "phase": "plan",
            "kind": "plan",
            "text": _plan_text(self.plan_tool),
            "icon": _tool_icon(self.plan_tool),
            "status": "done",
        }

    def ensure_plan(self, tool: str | None) -> tuple[str, dict[str, Any]] | None:
        if self.plan_emitted:
            if tool == self.plan_tool:
                return None
            self.plan_tool = tool
            return "update", self._build_plan_step(tool)
        self.plan_emitted = True
        self.plan_tool = tool
        return "add", self._build_plan_step(tool)

    def retract_generate(self) -> list[dict[str, Any]]:
        """工具介入时撤回「生成回答」，并重新打开思考计时。"""
        if not self.generate_emitted:
            return []
        self.generate_emitted = False
        self.thinking_finished_at = None
        self.finished = False
        return [
            {"type": "cot", "action": "remove", "step_id": "generate"},
            {"type": "cot", "action": "unfinish"},
        ]

    def maybe_start_generate(self) -> list[dict[str, Any]]:
        """开始生成回答：新增 generate 步骤，并结束思考计时。"""
        if self.generate_emitted:
            return []
        self.mark_thinking_done()
        self.generate_emitted = True
        events: list[dict[str, Any]] = [
            {
                "type": "cot",
                "action": "add",
                "step": {
                    "id": "generate",
                    "phase": "generate",
                    "kind": "generate",
                    "text": "生成回答",
                    "icon": "generate",
                    "status": "running",
                },
            }
        ]
        finish = self.finish_payload()
        if finish:
            events.append({"type": "cot", "action": "finish", **finish})
        return events

    def execute_start(self, tool: str, tool_call_id: str, raw_input: str) -> dict[str, Any]:
        return {
            "id": tool_call_id,
            "phase": "execute",
            "kind": "execute",
            "text": _execute_text(tool, raw_input),
            "tool": tool,
            "icon": _tool_icon(tool),
            "status": "running",
        }

    def execute_update(self, tool: str, tool_call_id: str, raw_input: str) -> dict[str, Any]:
        """工具参数流式到达后刷新执行文案。"""
        return {
            "id": tool_call_id,
            "phase": "execute",
            "kind": "execute",
            "text": _execute_text(tool, raw_input),
            "tool": tool,
            "icon": _tool_icon(tool),
            "status": "running",
        }

    def execute_end(self, tool: str, tool_call_id: str, raw_input: str, status: str) -> dict[str, Any]:
        ok = status == "success"
        return {
            "id": tool_call_id,
            "phase": "execute",
            "kind": "execute",
            "text": _execute_text(tool, raw_input, failed=not ok),
            "tool": tool,
            "icon": _tool_icon(tool),
            "status": "done" if ok else "error",
        }

    def generate_done(self) -> dict[str, Any]:
        return {
            "id": "generate",
            "phase": "generate",
            "kind": "generate",
            "text": "生成回答",
            "icon": "generate",
            "status": "done",
        }

    def mark_thinking_done(self) -> None:
        self.thinking_finished_at = time.monotonic()

    def finish_payload(self) -> dict[str, Any]:
        if self.finished:
            return {}
        self.finished = True
        end = self.thinking_finished_at or time.monotonic()
        duration_ms = int((end - self.started_at) * 1000)
        return {"duration_ms": max(duration_ms, 1)}


class CotTraceCollector:
    """根据 SSE cot 事件还原最终思考轨迹，供落库。"""

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []
        self.finished = False
        self.duration_ms: int | None = None

    def apply(self, event: dict[str, Any]) -> None:
        action = event.get("action")
        if action == "remove" and event.get("step_id"):
            step_id = event["step_id"]
            self.steps = [s for s in self.steps if s.get("id") != step_id]
            return
        if action == "unfinish":
            self.finished = False
            self.duration_ms = None
            return
        if action in ("add", "update") and isinstance(event.get("step"), dict):
            step = dict(event["step"])
            idx = next(
                (i for i, s in enumerate(self.steps) if s.get("id") == step.get("id")),
                -1,
            )
            if idx < 0:
                self.steps.append(step)
            else:
                self.steps[idx] = {**self.steps[idx], **step}
            return
        if action == "finish":
            self.finished = True
            duration = event.get("duration_ms")
            if isinstance(duration, int):
                self.duration_ms = duration
            for step in self.steps:
                if step.get("status") == "error":
                    continue
                # 生成步骤可能在 finish 后仍 running，由后续 generate_done 更新
                if (
                    step.get("status") == "running"
                    and step.get("phase") != "generate"
                    and step.get("kind") != "generate"
                ):
                    step["status"] = "done"

    def snapshot(self) -> dict[str, Any] | None:
        if not self.steps:
            return None
        steps: list[dict[str, Any]] = []
        for step in self.steps:
            item = dict(step)
            if item.get("status") == "running" or not item.get("status"):
                item["status"] = "done"
            steps.append(item)
        return {
            "steps": steps,
            "finished": True,
            "durationMs": self.duration_ms,
        }
