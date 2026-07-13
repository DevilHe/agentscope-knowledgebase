import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))  # admin | user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    slug: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeBaseRegistry(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("departments.id"), nullable=True)
    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserDepartment(Base):
    __tablename__ = "user_departments"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    department_id: Mapped[str] = mapped_column(String(36), ForeignKey("departments.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    knowledge_base: Mapped[str] = mapped_column(String(128), default="default")
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("departments.id"), nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(16), default="department")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="processing")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(36), index=True)
    knowledge_base: Mapped[str] = mapped_column(String(128), index=True)
    org_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    department_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(512), default="")
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(256), default="新对话")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    cot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    os: Mapped[str | None] = mapped_column(String(64), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


engine = create_engine(settings.mysql_url, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _migrate_users_columns(conn, insp) -> None:
    if not insp.has_table("users"):
        return
    existing = {col["name"] for col in insp.get_columns("users")}
    statements = []
    if "is_active" not in existing:
        statements.append("ALTER TABLE users ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1")
    if "failed_login_attempts" not in existing:
        statements.append("ALTER TABLE users ADD COLUMN failed_login_attempts INT NOT NULL DEFAULT 0")
    if "locked_until" not in existing:
        statements.append("ALTER TABLE users ADD COLUMN locked_until DATETIME NULL")
    if "updated_at" not in existing:
        statements.append(
            "ALTER TABLE users ADD COLUMN updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        )
    for stmt in statements:
        conn.execute(text(stmt))


def _migrate_documents_columns(conn, insp) -> None:
    if not insp.has_table("documents"):
        return
    existing = {col["name"] for col in insp.get_columns("documents")}
    statements = []
    if "version" not in existing:
        statements.append("ALTER TABLE documents ADD COLUMN version INT NOT NULL DEFAULT 1")
    if "content_hash" not in existing:
        statements.append("ALTER TABLE documents ADD COLUMN content_hash VARCHAR(64) NULL")
    if "parent_id" not in existing:
        statements.append("ALTER TABLE documents ADD COLUMN parent_id VARCHAR(36) NULL")
    if "is_latest" not in existing:
        statements.append("ALTER TABLE documents ADD COLUMN is_latest TINYINT(1) NOT NULL DEFAULT 1")
    if "org_id" not in existing:
        statements.append("ALTER TABLE documents ADD COLUMN org_id VARCHAR(36) NULL")
    if "department_id" not in existing:
        statements.append("ALTER TABLE documents ADD COLUMN department_id VARCHAR(36) NULL")
    if "visibility" not in existing:
        statements.append("ALTER TABLE documents ADD COLUMN visibility VARCHAR(16) NOT NULL DEFAULT 'department'")
    for stmt in statements:
        conn.execute(text(stmt))


def _migrate_document_chunks_columns(conn, insp) -> None:
    if not insp.has_table("document_chunks"):
        return
    existing = {col["name"] for col in insp.get_columns("document_chunks")}
    statements = []
    if "org_id" not in existing:
        statements.append("ALTER TABLE document_chunks ADD COLUMN org_id VARCHAR(36) NULL")
    if "department_id" not in existing:
        statements.append("ALTER TABLE document_chunks ADD COLUMN department_id VARCHAR(36) NULL")
    for stmt in statements:
        conn.execute(text(stmt))


def _ensure_chunk_fulltext_index(conn, insp) -> None:
    if not insp.has_table("document_chunks"):
        return
    indexes = insp.get_indexes("document_chunks")
    if any(idx.get("name") == "ft_content" for idx in indexes):
        return
    try:
        conn.execute(
            text("CREATE FULLTEXT INDEX ft_content ON document_chunks (content) WITH PARSER ngram")
        )
    except Exception:
        conn.execute(text("CREATE FULLTEXT INDEX ft_content ON document_chunks (content)"))


def _migrate_audit_logs_columns(conn, insp) -> None:
    if not insp.has_table("audit_logs"):
        return
    existing = {col["name"] for col in insp.get_columns("audit_logs")}
    statements = []
    if "os" not in existing:
        statements.append("ALTER TABLE audit_logs ADD COLUMN os VARCHAR(64) NULL")
    if "browser" not in existing:
        statements.append("ALTER TABLE audit_logs ADD COLUMN browser VARCHAR(64) NULL")
    if "device" not in existing:
        statements.append("ALTER TABLE audit_logs ADD COLUMN device VARCHAR(64) NULL")
    for stmt in statements:
        conn.execute(text(stmt))


def _migrate_chat_messages_columns(conn, insp) -> None:
    if not insp.has_table("chat_messages"):
        return
    existing = {col["name"] for col in insp.get_columns("chat_messages")}
    if "cot_json" not in existing:
        conn.execute(text("ALTER TABLE chat_messages ADD COLUMN cot_json TEXT NULL"))


def migrate_schema() -> None:
    """为已有库补充新列（无 Alembic 时的轻量迁移）。"""
    insp = inspect(engine)
    if not insp.has_table("users"):
        return
    with engine.begin() as conn:
        _migrate_users_columns(conn, insp)
        _migrate_documents_columns(conn, insp)
        _migrate_document_chunks_columns(conn, insp)
        _migrate_audit_logs_columns(conn, insp)
        _migrate_chat_messages_columns(conn, insp)
        _ensure_chunk_fulltext_index(conn, inspect(engine))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
