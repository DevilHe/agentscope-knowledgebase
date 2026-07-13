import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.audit.context import get_audit_context
from app.audit.user_agent import parse_user_agent
from app.db.models import AuditLog, User


def _truncate(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def record_audit(
    db: Session,
    *,
    action: str,
    status: str = "success",
    user: User | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    ctx = get_audit_context()
    user_id = user.id if user else ctx.get("user_id")
    username = user.username if user else ctx.get("username")
    ip = ip_address or ctx.get("ip")
    ua = user_agent if user_agent is not None else ctx.get("user_agent")
    os_name, browser, device = parse_user_agent(ua)

    payload = detail or {}
    if "content" in payload and isinstance(payload["content"], str):
        payload["content"] = _truncate(payload["content"])

    row = AuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        username=username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail_json=json.dumps(payload, ensure_ascii=False),
        ip_address=ip,
        os=os_name,
        browser=browser,
        device=device,
        status=status,
    )
    db.add(row)
    db.commit()
