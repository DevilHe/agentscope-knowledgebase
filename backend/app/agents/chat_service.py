import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta

from agentscope.message import Msg, TextBlock, UserMsg
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.agents.agent_stream import stream_agent_events
from app.agents.cot_builder import CotTraceCollector
from app.agents.governance import (
    check_user_token_quota,
    circuit_open_message,
    consume_user_tokens,
    estimate_tokens,
    is_circuit_open,
    record_agent_failure,
    record_agent_success,
    reply_timeout_seconds,
)
from app.audit.guard import check_sensitive_text, check_tool_quota, consume_tool_quota
from app.audit.service import record_audit
from app.config import settings
from app.db.models import ChatMessage, ChatSession, User
from app.services.llm import resolve_model_name
from app.services.source_trust import sources_view


def ensure_session(db: Session, user_id: str, session_id: str | None) -> str:
    sid = session_id or str(uuid.uuid4())
    session = db.get(ChatSession, sid)
    if session is None:
        db.add(
            ChatSession(
                id=sid,
                user_id=user_id,
                title="新对话",
                updated_at=datetime.utcnow(),
            )
        )
        db.commit()
    elif session.user_id != user_id:
        raise PermissionError("无权访问该会话")
    return sid


def load_history_messages(db: Session, session_id: str, limit: int) -> list[Msg]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(
            ChatMessage.created_at.asc(),
            case((ChatMessage.role == "user", 0), else_=1),
        )
        .all()
    )
    if len(rows) > limit:
        rows = rows[-limit:]
    messages: list[Msg] = []
    for row in rows:
        if row.role == "user":
            messages.append(UserMsg(name="user", content=row.content))
        elif row.role == "assistant":
            messages.append(
                Msg(
                    name="assistant",
                    content=[TextBlock(text=row.content)],
                    role="assistant",
                )
            )
    return messages


def save_messages(
    db: Session,
    session_id: str,
    question: str,
    answer: str,
    sources: list,
    cot: dict | None = None,
) -> str:
    now = datetime.utcnow()
    db.add(
        ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role="user",
            content=question,
            created_at=now,
        )
    )
    msg_id = str(uuid.uuid4())
    db.add(
        ChatMessage(
            id=msg_id,
            session_id=session_id,
            role="assistant",
            content=answer,
            sources_json=json.dumps(sources, ensure_ascii=False),
            cot_json=json.dumps(cot, ensure_ascii=False) if cot else None,
            created_at=now + timedelta(microseconds=1),
        )
    )
    session = db.get(ChatSession, session_id)
    if session:
        if session.title == "新对话" and question.strip():
            session.title = question.strip()[:48]
        session.updated_at = datetime.utcnow()
    db.commit()
    return msg_id


async def _consume_agent_stream(
    question: str,
    history: list[Msg],
    user: User,
    top_k: int,
    sources_collector: list[dict],
    model_name: str,
    deadline: float,
    cot_collector: CotTraceCollector | None = None,
) -> AsyncIterator[tuple[str, dict | list | str]]:
    """消费 Agent 事件流，向调用方 yield SSE 元组。"""
    async for event in stream_agent_events(
        question,
        history,
        user.role,
        top_k,
        sources_collector,
        user=user,
        model_name=model_name,
    ):
        if time.monotonic() > deadline:
            yield "error", {"message": "回答超时，请缩短问题后重试"}
            return

        event_type = event.get("type")
        if event_type == "meta":
            continue
        if event_type == "token":
            yield "token", {"delta": event["delta"]}
        elif event_type == "cot":
            if cot_collector is not None:
                cot_collector.apply(event)
            yield "cot", event
        elif event_type == "tool":
            yield "tool", event
        elif event_type == "error":
            yield "error", {"message": event.get("message", "Agent 执行失败")}
            return


async def stream_rag_answer(
    question: str,
    session_id: str | None,
    user: User,
    top_k: int,
    db: Session,
    ip_address: str | None = None,
    knowledge_bases: list[str] | None = None,
) -> AsyncIterator[tuple[str, dict | list | str]]:
    sensitive = check_sensitive_text(question)
    if sensitive:
        record_audit(
            db,
            action="chat_blocked",
            status="blocked",
            user=None,
            resource_type="session",
            resource_id=session_id,
            detail={"content": question, "reason": sensitive},
            ip_address=ip_address,
        )
        yield "error", {"message": sensitive}
        return

    if is_circuit_open():
        record_audit(
            db,
            action="chat_blocked",
            status="blocked",
            resource_type="session",
            resource_id=session_id,
            detail={"content": question, "reason": "circuit_open"},
            ip_address=ip_address,
        )
        yield "error", {"message": circuit_open_message()}
        return

    question_tokens = estimate_tokens(question)
    token_quota = check_user_token_quota(user.id, question_tokens)
    if token_quota:
        record_audit(
            db,
            action="chat_blocked",
            status="blocked",
            resource_type="session",
            resource_id=session_id,
            detail={"content": question, "reason": token_quota},
            ip_address=ip_address,
        )
        yield "error", {"message": token_quota}
        return

    llm_quota = check_tool_quota(user.id, "llm")
    if llm_quota:
        record_audit(
            db,
            action="chat_blocked",
            status="blocked",
            resource_type="session",
            resource_id=session_id,
            detail={"content": question, "reason": llm_quota},
            ip_address=ip_address,
        )
        yield "error", {"message": llm_quota}
        return

    consume_tool_quota(user.id, "llm")
    model_name = resolve_model_name("chat")
    record_audit(
        db,
        action="chat_question",
        resource_type="session",
        resource_id=session_id,
        detail={
            "content": question,
            "username": user.username,
            "knowledge_bases": knowledge_bases or [],
            "model": model_name,
            "max_tool_rounds": settings.agent_max_tool_rounds,
            "timeout_seconds": settings.agent_reply_timeout_seconds,
        },
        ip_address=ip_address,
    )
    record_audit(
        db,
        action="llm_call",
        resource_type="session",
        resource_id=session_id,
        detail={"model": model_name, "scene": "chat"},
        ip_address=ip_address,
    )

    sid = ensure_session(db, user.id, session_id)
    history = load_history_messages(db, sid, settings.history_max_messages)

    sources_collector: list[dict] = []
    chunks: list[str] = []
    cot_collector = CotTraceCollector()
    deadline = time.monotonic() + reply_timeout_seconds()
    used_model = model_name
    stream_failed = False

    try:
        async for kind, payload in _consume_agent_stream(
            question,
            history,
            user,
            top_k,
            sources_collector,
            model_name,
            deadline,
            cot_collector,
        ):
            if kind == "error":
                msg = payload.get("message", "")
                yield kind, payload
                if "工具调用已达上限" in msg or "回答超时" in msg:
                    return
                stream_failed = True
                record_agent_failure()
                return
            if kind == "token":
                chunks.append(payload["delta"])
            yield kind, payload
        record_agent_success()
    except Exception:
        stream_failed = True
        record_agent_failure()

    fallback_model = settings.openai_model_fallback.strip()
    if stream_failed and fallback_model and fallback_model != model_name:
        chunks = []
        sources_collector = []
        cot_collector = CotTraceCollector()
        used_model = fallback_model
        record_audit(
            db,
            action="llm_call",
            resource_type="session",
            resource_id=session_id,
            detail={"model": fallback_model, "scene": "fallback"},
            ip_address=ip_address,
        )
        try:
            async for kind, payload in _consume_agent_stream(
                question,
                history,
                user,
                top_k,
                sources_collector,
                fallback_model,
                deadline,
                cot_collector,
            ):
                if kind == "error":
                    yield kind, payload
                    return
                if kind == "token":
                    chunks.append(payload["delta"])
                yield kind, payload
            record_agent_success()
            stream_failed = False
        except Exception:
            record_agent_failure()
            yield "error", {"message": "模型服务暂时不可用，请稍后重试"}
            return

    if stream_failed:
        yield "error", {"message": "模型服务暂时不可用，请稍后重试"}
        return

    answer = "".join(chunks)
    consume_user_tokens(user.id, estimate_tokens(question + answer))

    sources_payload = sources_view(answer, sources_collector)
    final_sources = sources_payload["items"]
    intent = "rag" if final_sources else "general"
    cot_snapshot = cot_collector.snapshot()

    yield "sources", sources_payload
    yield "intent", {"intent": intent}

    msg_id = save_messages(db, sid, question, answer, final_sources, cot=cot_snapshot)
    yield "done", {
        "session_id": sid,
        "message_id": msg_id,
        "used_rag": bool(final_sources),
        "show_sources": sources_payload["show_sources"],
        "intent": intent,
        "model": used_model,
    }
