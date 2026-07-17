# -*- coding: utf-8 -*-
"""多轮对话历史压缩：超阈值时用 LLM 摘要旧轮次，保留最近若干条原文。"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.config import settings
from app.services.llm import invoke_text

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = """你是对话摘要助手。请将下列历史对话压缩成一段简洁的中文摘要，保留：
- 用户关注的主题与约束
- 已确认的关键事实、结论、偏好
- 未完成的待办或明确约定

不要复述寒暄；不要编造原文没有的信息；控制在 300 字以内。
直接输出摘要正文，不要加标题。

历史对话：
{dialogue}
"""


def _format_dialogue(messages: list[BaseMessage]) -> str:
    lines: list[str] = []
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        content = (content or "").strip()
        if not content:
            continue
        if isinstance(msg, HumanMessage):
            role = "用户"
        elif isinstance(msg, AIMessage):
            role = "助手"
        else:
            role = "系统"
        lines.append(f"{role}：{content}")
    return "\n".join(lines)


def rows_to_messages(rows) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for row in rows:
        if row.role == "user":
            messages.append(HumanMessage(content=row.content))
        elif row.role == "assistant":
            messages.append(AIMessage(content=row.content))
    return messages


async def compress_history_messages(
    messages: list[BaseMessage],
) -> list[BaseMessage]:
    """超阈值时：旧轮次 → 一条 SystemMessage 摘要 + 最近若干条原文。

    未超阈值或关闭压缩时原样返回。
    摘要失败时回退为仅保留最近若干条原文。
    """
    if not messages:
        return []

    enabled = settings.history_compress_enabled
    threshold = max(1, settings.history_compress_threshold)
    keep_recent = max(1, settings.history_keep_recent)

    if not enabled or len(messages) <= threshold:
        return messages

    # 保证至少能切出「旧段」；keep_recent 过大时压到 threshold-1
    keep = min(keep_recent, threshold - 1, len(messages) - 1)
    if keep < 1:
        return messages

    older = messages[:-keep]
    recent = messages[-keep:]
    if not older:
        return messages

    dialogue = _format_dialogue(older)
    if not dialogue.strip():
        return recent

    try:
        summary = await invoke_text(
            _SUMMARY_PROMPT.format(dialogue=dialogue),
            scene="chat",
        )
        summary = (summary or "").strip()
        if not summary:
            logger.warning("历史摘要为空，回退为仅保留最近 %s 条", keep)
            return recent
        summary_msg = SystemMessage(
            content=(
                "【历史对话摘要】以下为更早轮次的压缩摘要，供回答时参考；"
                "其后消息为最近原文。\n"
                f"{summary}"
            )
        )
        return [summary_msg, *recent]
    except Exception as exc:
        logger.warning("历史摘要失败，回退为仅保留最近 %s 条: %s", keep, exc)
        return recent
