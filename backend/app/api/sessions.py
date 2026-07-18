from datetime import datetime
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, exists
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db.models import ChatMessage, ChatSession, User, get_db
from app.services.source_trust import sources_view
from app.utils.datetime_ser import to_utc_iso

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionItem(BaseModel):
    id: str
    title: str
    created_at: str | None
    updated_at: str | None


class MessageItem(BaseModel):
    id: str
    role: str
    content: str
    sources: list | None = None
    show_sources: bool = False
    cot: dict | None = None
    created_at: str | None


class CreateSessionResponse(BaseModel):
    id: str
    title: str


class UpdateSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=256)


@router.get("")
def list_sessions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(ChatSession)
        .filter(
            ChatSession.user_id == user.id,
            exists().where(ChatMessage.session_id == ChatSession.id),
        )
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return {
        "items": [
            SessionItem(
                id=s.id,
                title=s.title,
                created_at=to_utc_iso(s.created_at),
                updated_at=to_utc_iso(s.updated_at),
            ).model_dump()
            for s in rows
        ]
    }


@router.post("")
def create_session(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    import uuid

    sid = str(uuid.uuid4())
    session = ChatSession(id=sid, user_id=user.id, title="新对话", updated_at=datetime.utcnow())
    db.add(session)
    db.commit()
    return CreateSessionResponse(id=sid, title=session.title)


@router.get("/{session_id}/messages")
def list_messages(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(
            ChatMessage.created_at.asc(),
            case((ChatMessage.role == "user", 0), else_=1),
        )
        .all()
    )
    items = []
    for row in rows:
        raw_sources = None
        if row.sources_json:
            raw_sources = json.loads(row.sources_json)
        raw_cot = None
        if row.cot_json:
            try:
                parsed = json.loads(row.cot_json)
                if isinstance(parsed, dict) and parsed.get("steps"):
                    raw_cot = parsed
            except json.JSONDecodeError:
                raw_cot = None
        view = (
            sources_view(row.content, raw_sources)
            if row.role == "assistant"
            else {"show_sources": False, "items": None}
        )
        items.append(
            MessageItem(
                id=row.id,
                role=row.role,
                content=row.content,
                sources=view["items"] or None,
                show_sources=view["show_sources"],
                cot=raw_cot,
                created_at=to_utc_iso(row.created_at),
            ).model_dump()
        )
    return {"items": items}


@router.patch("/{session_id}")
def update_session(
    session_id: str,
    body: UpdateSessionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    session.title = body.title
    session.updated_at = datetime.utcnow()
    db.commit()
    return {"id": session.id, "title": session.title}


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.delete(session)
    db.commit()
