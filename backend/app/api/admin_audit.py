import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import require_admin
from app.utils.datetime_ser import to_utc_iso
from app.db.models import AuditLog, User, get_db

router = APIRouter(prefix="/admin/audit-logs", tags=["admin-audit"])


@router.get("")
def list_audit_logs(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    action: str | None = None,
    username: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if username:
        query = query.filter(AuditLog.username.like(f"%{username}%"))
    if status:
        query = query.filter(AuditLog.status == status)

    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items: list[dict[str, Any]] = []
    for row in rows:
        detail: dict[str, Any] | None = None
        if row.detail_json:
            try:
                detail = json.loads(row.detail_json)
            except json.JSONDecodeError:
                detail = {"raw": row.detail_json}
        items.append(
            {
                "id": row.id,
                "user_id": row.user_id,
                "username": row.username,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "detail": detail,
                "ip_address": row.ip_address,
                "os": row.os,
                "browser": row.browser,
                "device": row.device,
                "status": row.status,
                "created_at": to_utc_iso(row.created_at),
            }
        )

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/actions")
def list_audit_actions(_: User = Depends(require_admin)):
    return {
        "items": [
            {"value": "doc_upload", "label": "文档上传"},
            {"value": "doc_delete", "label": "文档删除"},
            {"value": "doc_upload_rejected", "label": "文档上传拦截"},
            {"value": "chat_question", "label": "聊天提问"},
            {"value": "chat_blocked", "label": "聊天拦截"},
            {"value": "tool_web_search", "label": "联网搜索"},
            {"value": "tool_get_weather", "label": "天气查询"},
            {"value": "tool_search_knowledge_base", "label": "知识库检索"},
            {"value": "tool_blocked", "label": "工具调用拦截"},
            {"value": "llm_call", "label": "LLM 调用"},
        ]
    }
