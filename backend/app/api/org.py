from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_admin
from app.config import settings
from app.db.models import Department, Organization, User, get_db
from app.services.acl import list_accessible_knowledge_bases, resolve_scope

router = APIRouter(prefix="/org", tags=["org"])


@router.get("/departments/public")
def list_departments_public(db: Session = Depends(get_db)):
    """注册页选择部门（无需登录）。"""
    if not settings.registration_enabled:
        raise HTTPException(status_code=404, detail="未开放注册")
    org = db.query(Organization).filter(Organization.slug == "default").first()
    if not org:
        return {"items": []}
    rows = (
        db.query(Department)
        .filter(Department.org_id == org.id)
        .order_by(Department.name.asc())
        .all()
    )
    return {"items": [{"id": row.id, "name": row.name, "slug": row.slug} for row in rows]}


@router.get("/departments")
def list_departments(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    scope = resolve_scope(db, _)
    rows = (
        db.query(Department)
        .filter(Department.org_id == scope.org_id)
        .order_by(Department.name.asc())
        .all()
    )
    return {
        "items": [
            {"id": row.id, "name": row.name, "slug": row.slug}
            for row in rows
        ]
    }


@router.get("/knowledge-bases")
def list_knowledge_bases(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = list_accessible_knowledge_bases(db, user)
    return {
        "items": [
            {
                "id": item.id,
                "slug": item.slug,
                "name": item.name,
                "department_id": item.department_id,
                "department_name": item.department_name,
            }
            for item in items
        ]
    }
