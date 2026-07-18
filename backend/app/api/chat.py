import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.agents.chat_service import stream_rag_answer
from app.audit.context import set_audit_context
from app.auth.deps import get_client_ip, get_current_user, get_user_agent
from app.config import settings
from app.db.models import User, get_db
from app.services.acl import list_retrieval_knowledge_bases

router = APIRouter(prefix="/chat", tags=["chat"])


class RagChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = None
    top_k: int = Field(default=settings.top_k, ge=1, le=10)


@router.post("/rag")
async def rag_chat(
    body: RagChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ip = get_client_ip(request)
    set_audit_context(
        user_id=user.id,
        username=user.username,
        ip=ip,
        user_agent=get_user_agent(request),
    )

    async def event_generator():
        try:
            kb_slugs = list_retrieval_knowledge_bases(db, user)
            if not kb_slugs:
                yield {
                    "event": "error",
                    "data": json.dumps({"message": "未分配可访问知识库"}, ensure_ascii=False),
                }
                return
            async for event, data in stream_rag_answer(
                question=body.question,
                session_id=body.session_id,
                user=user,
                top_k=body.top_k,
                db=db,
                ip_address=ip,
                knowledge_bases=kb_slugs,
            ):
                payload = json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else data
                yield {"event": event, "data": payload}
        except PermissionError:
            yield {
                "event": "error",
                "data": json.dumps({"message": "无权访问该会话"}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
