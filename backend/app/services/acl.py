# -*- coding: utf-8 -*-
"""组织 / 部门 / 知识库 / 文档级 ACL。"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Query, Session

from app.db.models import Document, KnowledgeBaseRegistry, User, UserDepartment

VISIBILITY_ORG = "org"
VISIBILITY_DEPARTMENT = "department"
VISIBILITY_PRIVATE = "private"


@dataclass(frozen=True)
class AccessScope:
    org_id: str
    department_ids: frozenset[str]
    is_super_admin: bool


@dataclass(frozen=True)
class KnowledgeBaseInfo:
    id: str
    slug: str
    name: str
    department_id: str | None
    department_name: str | None


def is_super_admin(user: User) -> bool:
    return user.role == "admin"


def get_user_department_ids(db: Session, user: User) -> frozenset[str]:
    rows = db.query(UserDepartment.department_id).filter(UserDepartment.user_id == user.id).all()
    return frozenset(row[0] for row in rows)


def resolve_scope(db: Session, user: User) -> AccessScope:
    org = _default_org(db)
    if is_super_admin(user):
        return AccessScope(org_id=org.id, department_ids=frozenset(), is_super_admin=True)
    return AccessScope(
        org_id=org.id,
        department_ids=get_user_department_ids(db, user),
        is_super_admin=False,
    )


def _default_org(db: Session):
    from app.db.models import Organization

    org = db.query(Organization).filter(Organization.slug == "default").first()
    if not org:
        raise HTTPException(status_code=500, detail="组织未初始化")
    return org


def list_accessible_knowledge_bases(db: Session, user: User) -> list[KnowledgeBaseInfo]:
    from app.db.models import Department

    scope = resolve_scope(db, user)
    query = db.query(KnowledgeBaseRegistry).filter(KnowledgeBaseRegistry.org_id == scope.org_id)
    if not scope.is_super_admin:
        dept_ids = list(scope.department_ids)
        query = query.filter(
            (KnowledgeBaseRegistry.department_id.is_(None))
            | (KnowledgeBaseRegistry.department_id.in_(dept_ids))
        )
    rows = query.order_by(KnowledgeBaseRegistry.name.asc()).all()
    dept_map = {
        d.id: d.name
        for d in db.query(Department).filter(Department.org_id == scope.org_id).all()
    }
    return [
        KnowledgeBaseInfo(
            id=row.id,
            slug=row.slug,
            name=row.name,
            department_id=row.department_id,
            department_name=dept_map.get(row.department_id) if row.department_id else None,
        )
        for row in rows
    ]


def get_kb_registry(db: Session, kb_slug: str) -> KnowledgeBaseRegistry | None:
    scope_org = _default_org(db)
    return (
        db.query(KnowledgeBaseRegistry)
        .filter(
            KnowledgeBaseRegistry.org_id == scope_org.id,
            KnowledgeBaseRegistry.slug == kb_slug,
        )
        .first()
    )


def assert_kb_read_access(db: Session, user: User, kb_slug: str) -> KnowledgeBaseRegistry:
    kb = get_kb_registry(db, kb_slug)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    if is_super_admin(user):
        return kb
    accessible = {item.slug for item in list_accessible_knowledge_bases(db, user)}
    if kb_slug not in accessible:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该知识库")
    return kb


def assert_kb_write_access(db: Session, user: User, kb_slug: str) -> KnowledgeBaseRegistry:
    kb = assert_kb_read_access(db, user, kb_slug)
    if not is_super_admin(user):
        if kb.department_id and kb.department_id not in get_user_department_ids(db, user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权写入该知识库")
    return kb


def can_read_document(db: Session, user: User, doc: Document) -> bool:
    scope = resolve_scope(db, user)
    try:
        assert_kb_read_access(db, user, doc.knowledge_base)
    except HTTPException:
        return False

    visibility = doc.visibility or VISIBILITY_DEPARTMENT
    if scope.is_super_admin:
        return True
    if visibility == VISIBILITY_ORG:
        return True
    if visibility == VISIBILITY_PRIVATE:
        return scope.is_super_admin
    if visibility == VISIBILITY_DEPARTMENT:
        if not doc.department_id:
            return True
        return doc.department_id in scope.department_ids
    return False


def assert_document_read_access(db: Session, user: User, doc: Document) -> None:
    if not can_read_document(db, user, doc):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该文档")


def assert_document_write_access(db: Session, user: User, doc: Document) -> None:
    if not is_super_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    assert_document_read_access(db, user, doc)


def filter_documents_query(db: Session, user: User, query: Query) -> Query:
    scope = resolve_scope(db, user)
    query = query.filter(Document.org_id == scope.org_id)
    if scope.is_super_admin:
        return query

    accessible_kbs = [item.slug for item in list_accessible_knowledge_bases(db, user)]
    if not accessible_kbs:
        return query.filter(Document.id == "__none__")

    dept_ids = list(scope.department_ids)
    return query.filter(
        Document.knowledge_base.in_(accessible_kbs),
        (
            (Document.visibility == VISIBILITY_ORG)
            | (
                (Document.visibility == VISIBILITY_DEPARTMENT)
                & (
                    Document.department_id.is_(None)
                    | Document.department_id.in_(dept_ids)
                )
            )
        ),
    )


def allowed_doc_ids_for_retrieval(db: Session, user: User, kb_slug: str) -> set[str] | None:
    """返回允许检索的 doc_id 集合；None 表示该 KB 下全部文档（管理员）。"""
    assert_kb_read_access(db, user, kb_slug)
    scope = resolve_scope(db, user)
    if scope.is_super_admin:
        return None

    query = (
        db.query(Document.id)
        .filter(
            Document.org_id == scope.org_id,
            Document.knowledge_base == kb_slug,
            Document.is_latest.is_(True),
            Document.status == "done",
        )
    )
    query = filter_documents_query(db, user, query)
    return {row[0] for row in query.all()}


def list_retrieval_knowledge_bases(db: Session, user: User) -> list[str]:
    """返回聊天检索应覆盖的知识库列表（按用户权限）。"""
    scope = resolve_scope(db, user)
    if scope.is_super_admin:
        rows = (
            db.query(KnowledgeBaseRegistry.slug)
            .filter(KnowledgeBaseRegistry.org_id == scope.org_id)
            .order_by(KnowledgeBaseRegistry.name.asc())
            .all()
        )
        return [row[0] for row in rows]
    return [item.slug for item in list_accessible_knowledge_bases(db, user)]


def allowed_doc_ids_for_user_retrieval(db: Session, user: User) -> set[str] | None:
    """返回用户可检索的全部 doc_id；None 表示不限制（管理员）。"""
    scope = resolve_scope(db, user)
    if scope.is_super_admin:
        return None

    query = (
        db.query(Document.id)
        .filter(
            Document.is_latest.is_(True),
            Document.status == "done",
        )
    )
    query = filter_documents_query(db, user, query)
    return {row[0] for row in query.all()}


def resolve_chat_knowledge_base(db: Session, user: User, requested_kb: str | None) -> str:
    accessible = list_accessible_knowledge_bases(db, user)
    if not accessible:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="未分配可访问知识库")

    if requested_kb:
        assert_kb_read_access(db, user, requested_kb)
        return requested_kb

    for item in accessible:
        if item.slug == "default":
            return item.slug
    return accessible[0].slug
