from typing import Any

from app.audit.context import get_audit_context
from app.audit.guard import check_sensitive_text, check_tool_quota, consume_tool_quota
from app.audit.service import record_audit
from app.db.models import SessionLocal

_TOOL_QUOTA_KEY: dict[str, str | None] = {
    "web_search": "web_search",
    "get_weather": "get_weather",
    "search_knowledge_base": None,
}


def _tool_action(tool_name: str) -> str:
    return f"tool_{tool_name}"


def _audit_tool(
    tool_name: str,
    payload: dict[str, Any],
    *,
    status: str,
    reason: str | None = None,
) -> None:
    detail = dict(payload)
    if reason:
        detail["reason"] = reason
    db = SessionLocal()
    try:
        record_audit(
            db,
            action=_tool_action(tool_name) if status == "success" else "tool_blocked",
            status=status,
            resource_type="tool",
            resource_id=tool_name,
            detail=detail,
        )
    finally:
        db.close()


def guard_tool_call(tool_name: str, payload: dict[str, Any]) -> str | None:
    """工具调用前校验，被拦截时返回错误信息。"""
    text = " ".join(str(v) for v in payload.values() if v is not None)
    sensitive = check_sensitive_text(text)
    if sensitive:
        _audit_tool(tool_name, payload, status="blocked", reason=sensitive)
        return sensitive

    ctx = get_audit_context()
    user_id = ctx.get("user_id")
    quota_key = _TOOL_QUOTA_KEY.get(tool_name)
    if user_id and quota_key:
        quota_msg = check_tool_quota(user_id, quota_key)
        if quota_msg:
            _audit_tool(tool_name, payload, status="blocked", reason=quota_msg)
            return quota_msg

    return None


def consume_tool_call(tool_name: str) -> None:
    ctx = get_audit_context()
    user_id = ctx.get("user_id")
    quota_key = _TOOL_QUOTA_KEY.get(tool_name)
    if user_id and quota_key:
        consume_tool_quota(user_id, quota_key)


def audit_tool_success(tool_name: str, payload: dict[str, Any]) -> None:
    _audit_tool(tool_name, payload, status="success")
