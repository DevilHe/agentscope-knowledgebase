import hashlib
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.service import record_audit
from app.auth.deps import get_client_ip, get_current_user, get_user_agent, require_admin
from app.config import settings
from app.db.models import Document, User, get_db
from app.db.redis_client import get_task_status, set_task_status
from app.ingest.pipeline import run_ingest
from app.ingest.upload_paths import (
    remove_stored_file,
    resolve_stored_file,
    stored_upload_path,
)
from app.ingest.upload_validation import validate_upload_content
from app.services.acl import (
    VISIBILITY_DEPARTMENT,
    VISIBILITY_ORG,
    VISIBILITY_PRIVATE,
    assert_document_write_access,
    assert_kb_write_access,
    filter_documents_query,
    resolve_scope,
)
from app.services.chunk_store import delete_chunks_by_doc
from app.services.knowledge_base import delete_doc_vectors
from app.utils.datetime_ser import to_utc_iso

router = APIRouter(prefix="/admin/documents", tags=["admin-documents"])


class UpdateDocumentRequest(BaseModel):
    knowledge_base: str | None = None
    visibility: str | None = None


def _ingest_background(
    doc_id: str,
    task_id: str,
    file_path: str,
    filename: str,
    knowledge_base: str,
    org_id: str,
    department_id: str | None,
    replace_doc_id: str | None = None,
):
    run_ingest(
        doc_id,
        task_id,
        file_path,
        filename,
        knowledge_base,
        org_id=org_id,
        department_id=department_id,
        replace_doc_id=replace_doc_id,
    )


def _doc_to_dict(doc: Document, db: Session) -> dict:
    from app.db.models import Department

    dept_name = None
    if doc.department_id:
        dept = db.get(Department, doc.department_id)
        dept_name = dept.name if dept else None
    visibility_labels = {
        VISIBILITY_ORG: "全公司",
        VISIBILITY_DEPARTMENT: "本部门",
        VISIBILITY_PRIVATE: "仅管理员",
    }
    return {
        "id": doc.id,
        "filename": doc.filename,
        "knowledge_base": doc.knowledge_base,
        "org_id": doc.org_id,
        "department_id": doc.department_id,
        "department_name": dept_name,
        "visibility": doc.visibility,
        "visibility_label": visibility_labels.get(doc.visibility or VISIBILITY_DEPARTMENT, doc.visibility),
        "chunk_count": doc.chunk_count,
        "status": doc.status,
        "error_message": doc.error_message,
        "uploaded_by": doc.uploaded_by,
        "version": doc.version,
        "content_hash": doc.content_hash,
        "parent_id": doc.parent_id,
        "is_latest": doc.is_latest,
        "created_at": to_utc_iso(doc.created_at),
    }


@router.get("")
def list_documents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Document).filter(Document.is_latest.is_(True))
    query = filter_documents_query(db, user, query)
    docs = query.order_by(Document.created_at.desc()).all()
    return {"items": [_doc_to_dict(d, db) for d in docs]}


@router.post("/upload")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    knowledge_base: str = settings.knowledge_base,
    department_id: str | None = None,
    visibility: str = VISIBILITY_DEPARTMENT,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if visibility not in {VISIBILITY_ORG, VISIBILITY_DEPARTMENT, VISIBILITY_PRIVATE}:
        raise HTTPException(status_code=400, detail="无效的可见范围")

    kb = assert_kb_write_access(db, admin, knowledge_base)
    scope = resolve_scope(db, admin)
    filename = file.filename or "unknown"
    ip = get_client_ip(request)
    user_agent = get_user_agent(request)

    try:
        content = await file.read()
        validate_upload_content(filename, content)
    except HTTPException as exc:
        record_audit(
            db,
            action="doc_upload_rejected",
            status="blocked",
            user=admin,
            resource_type="document",
            detail={"filename": filename, "reason": exc.detail},
            ip_address=ip,
            user_agent=user_agent,
        )
        raise

    content_hash = hashlib.sha256(content).hexdigest()
    target_department_id = department_id or kb.department_id
    if visibility == VISIBILITY_DEPARTMENT and not target_department_id:
        raise HTTPException(status_code=400, detail="部门可见文档需指定部门")

    existing = (
        db.query(Document)
        .filter(
            Document.filename == filename,
            Document.knowledge_base == knowledge_base,
            Document.is_latest.is_(True),
        )
        .first()
    )

    if existing and existing.content_hash == content_hash:
        record_audit(
            db,
            action="doc_upload_unchanged",
            user=admin,
            resource_type="document",
            resource_id=existing.id,
            detail={"filename": filename, "version": existing.version},
            ip_address=ip,
            user_agent=user_agent,
        )
        return {
            "doc_id": existing.id,
            "task_id": None,
            "status": "unchanged",
            "version": existing.version,
            "message": "内容与当前版本相同，无需更新",
        }

    replace_doc_id: str | None = None
    version = 1
    parent_id: str | None = None
    if existing:
        existing.is_latest = False
        replace_doc_id = existing.id
        version = existing.version + 1
        parent_id = existing.id
        db.commit()

    doc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    dest = stored_upload_path(knowledge_base, filename)
    dest.write_bytes(content)

    doc = Document(
        id=doc_id,
        filename=filename,
        knowledge_base=knowledge_base,
        org_id=scope.org_id,
        department_id=target_department_id,
        visibility=visibility,
        status="processing",
        uploaded_by=admin.id,
        version=version,
        content_hash=content_hash,
        parent_id=parent_id,
        is_latest=True,
    )
    db.add(doc)
    db.commit()

    record_audit(
        db,
        action="doc_upload",
        user=admin,
        resource_type="document",
        resource_id=doc_id,
        detail={
            "filename": filename,
            "size_bytes": len(content),
            "knowledge_base": knowledge_base,
            "department_id": target_department_id,
            "visibility": visibility,
            "version": version,
            "replaced_doc_id": replace_doc_id,
        },
        ip_address=ip,
        user_agent=user_agent,
    )

    set_task_status(task_id, {"doc_id": doc_id, "status": "processing", "chunk_count": 0})
    background_tasks.add_task(
        _ingest_background,
        doc_id,
        task_id,
        str(dest),
        filename,
        knowledge_base,
        scope.org_id,
        target_department_id,
        replace_doc_id,
    )

    return {
        "doc_id": doc_id,
        "task_id": task_id,
        "status": "processing",
        "version": version,
    }


@router.get("/tasks/{task_id}")
def get_task(task_id: str, _: User = Depends(require_admin)):
    task = get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.patch("/{doc_id}")
async def update_document(
    doc_id: str,
    body: UpdateDocumentRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    assert_document_write_access(db, admin, doc)

    if not body.knowledge_base and not body.visibility:
        raise HTTPException(status_code=400, detail="未提供可更新字段")

    scope = resolve_scope(db, admin)
    old_kb_slug = doc.knowledge_base
    kb_changed = False
    reingest = False

    if body.visibility is not None:
        if body.visibility not in {VISIBILITY_ORG, VISIBILITY_DEPARTMENT, VISIBILITY_PRIVATE}:
            raise HTTPException(status_code=400, detail="无效的可见范围")
        doc.visibility = body.visibility

    if body.knowledge_base is not None:
        kb = assert_kb_write_access(db, admin, body.knowledge_base)
        if body.knowledge_base != doc.knowledge_base:
            doc.knowledge_base = body.knowledge_base
            doc.department_id = kb.department_id
            kb_changed = True
            reingest = doc.status == "done" and doc.chunk_count > 0

    visibility = doc.visibility or VISIBILITY_DEPARTMENT
    if visibility == VISIBILITY_DEPARTMENT and not doc.department_id:
        raise HTTPException(status_code=400, detail="本部门可见文档需有所属部门")

    if kb_changed and reingest:
        await delete_doc_vectors(doc_id, old_kb_slug)
        stored = resolve_stored_file(doc.filename, old_kb_slug)
        if stored and stored.is_file():
            # 知识库变更时把文件挪到新 kb 目录，仍保持原文件名
            new_dest = stored_upload_path(doc.knowledge_base, doc.filename)
            if stored.resolve() != new_dest.resolve():
                new_dest.parent.mkdir(parents=True, exist_ok=True)
                new_dest.write_bytes(stored.read_bytes())
                stored.unlink(missing_ok=True)
                stored = new_dest
            doc.status = "processing"
            task_id = str(uuid.uuid4())
            db.commit()
            set_task_status(task_id, {"doc_id": doc_id, "status": "processing", "chunk_count": 0})
            background_tasks.add_task(
                _ingest_background,
                doc_id,
                task_id,
                str(stored),
                doc.filename,
                doc.knowledge_base,
                scope.org_id,
                doc.department_id,
            )
        else:
            from app.db.models import DocumentChunk

            db.query(DocumentChunk).filter(DocumentChunk.doc_id == doc_id).update(
                {"knowledge_base": doc.knowledge_base}
            )
            db.commit()
    else:
        db.commit()

    record_audit(
        db,
        action="doc_update",
        user=admin,
        resource_type="document",
        resource_id=doc_id,
        detail={
            "filename": doc.filename,
            "knowledge_base": doc.knowledge_base,
            "visibility": doc.visibility,
            "kb_changed": kb_changed,
        },
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    return _doc_to_dict(doc, db)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    assert_document_write_access(db, admin, doc)

    filename = doc.filename
    was_latest = doc.is_latest
    parent_id = doc.parent_id
    doc_version = doc.version

    await delete_doc_vectors(doc_id, doc.knowledge_base)
    delete_chunks_by_doc(db, doc_id)

    # 仅当没有其他文档仍引用同 kb + 同文件名时，才删除落盘文件
    siblings = (
        db.query(Document.id)
        .filter(
            Document.id != doc_id,
            Document.filename == filename,
            Document.knowledge_base == doc.knowledge_base,
        )
        .count()
    )
    if siblings == 0:
        remove_stored_file(filename, doc.knowledge_base)

    db.delete(doc)
    db.commit()

    if was_latest and parent_id:
        parent = db.get(Document, parent_id)
        if parent:
            parent.is_latest = True
            db.commit()

    record_audit(
        db,
        action="doc_delete",
        user=admin,
        resource_type="document",
        resource_id=doc_id,
        detail={"filename": filename, "version": doc_version},
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
