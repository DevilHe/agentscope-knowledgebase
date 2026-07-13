import uuid

from sqlalchemy.orm import Session

from app.auth.password import hash_password
from app.config import settings
from app.db.models import (
    Department,
    Document,
    KnowledgeBaseRegistry,
    Organization,
    User,
    UserDepartment,
)
from app.services.acl import VISIBILITY_ORG


def seed_users(db: Session) -> None:
    org, departments, kbs = seed_org_structure(db)

    defaults = [
        (settings.admin_username, settings.admin_password, "admin", None),
        (settings.user_username, settings.user_password, "user", "rnd"),
    ]
    for username, password, role, dept_slug in defaults:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            existing.role = role
            existing.is_active = True
            user = existing
        else:
            user = User(
                id=str(uuid.uuid4()),
                username=username,
                password_hash=hash_password(password),
                role=role,
                is_active=True,
            )
            db.add(user)
            db.flush()

        db.query(UserDepartment).filter(UserDepartment.user_id == user.id).delete()
        if dept_slug:
            dept = departments.get(dept_slug)
            if dept:
                db.add(UserDepartment(user_id=user.id, department_id=dept.id))

    _backfill_documents(db, org.id)
    db.commit()


def seed_org_structure(db: Session) -> tuple[Organization, dict[str, Department], dict[str, KnowledgeBaseRegistry]]:
    org = db.query(Organization).filter(Organization.slug == "default").first()
    if not org:
        org = Organization(id=str(uuid.uuid4()), name="默认企业", slug="default")
        db.add(org)
        db.flush()

    dept_specs = [
        ("rnd", "研发部"),
        ("product", "产品部"),
        ("hr", "人力行政部"),
    ]
    departments: dict[str, Department] = {}
    for slug, name in dept_specs:
        dept = (
            db.query(Department)
            .filter(Department.org_id == org.id, Department.slug == slug)
            .first()
        )
        if not dept:
            dept = Department(id=str(uuid.uuid4()), org_id=org.id, slug=slug, name=name)
            db.add(dept)
            db.flush()
        departments[slug] = dept

    kb_specs = [
        ("default", "全公司共享库", None, "全员可见的制度与通用文档"),
        ("rnd-kb", "研发知识库", "rnd", "研发部技术文档与规范"),
        ("product-kb", "产品知识库", "product", "产品部需求与方案"),
        ("hr-kb", "人力行政知识库", "hr", "人事制度与行政流程"),
    ]
    kbs: dict[str, KnowledgeBaseRegistry] = {}
    for slug, name, dept_slug, desc in kb_specs:
        kb = (
            db.query(KnowledgeBaseRegistry)
            .filter(KnowledgeBaseRegistry.org_id == org.id, KnowledgeBaseRegistry.slug == slug)
            .first()
        )
        if not kb:
            kb = KnowledgeBaseRegistry(
                id=str(uuid.uuid4()),
                org_id=org.id,
                department_id=departments[dept_slug].id if dept_slug else None,
                slug=slug,
                name=name,
                description=desc,
            )
            db.add(kb)
            db.flush()
        kbs[slug] = kb

    db.flush()
    return org, departments, kbs


def _backfill_documents(db: Session, org_id: str) -> None:
    docs = db.query(Document).filter(Document.org_id.is_(None)).all()
    for doc in docs:
        doc.org_id = org_id
        if doc.knowledge_base == "default":
            doc.visibility = VISIBILITY_ORG
            doc.department_id = None
        else:
            kb = (
                db.query(KnowledgeBaseRegistry)
                .filter(KnowledgeBaseRegistry.org_id == org_id, KnowledgeBaseRegistry.slug == doc.knowledge_base)
                .first()
            )
            if kb:
                doc.department_id = kb.department_id
    db.flush()
