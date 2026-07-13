import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt
from sqlalchemy.orm import Session

from app.auth.password import hash_password, verify_password
from app.auth.password_policy import validate_password
from app.auth.username_policy import validate_username
from app.auth.token_store import (
    blacklist_jti,
    clear_user_session,
    invalidate_user_sessions,
    revoke_refresh_token,
    start_user_session,
    store_refresh_token,
)
from app.config import settings
from app.db.models import Department, User, UserDepartment


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def _create_token_payload(user: User, token_type: str, expire: datetime, session_id: str) -> dict:
    return {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "type": token_type,
        "sid": session_id,
        "jti": str(uuid.uuid4()),
        "exp": expire,
    }


def create_access_token(user: User, session_id: str) -> tuple[str, str, float]:
    expire = _utcnow() + timedelta(hours=settings.jwt_expire_hours)
    payload = _create_token_payload(user, "access", expire, session_id)
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, payload["jti"], expire.timestamp()


def create_refresh_token(user: User, session_id: str) -> str:
    token = secrets.token_urlsafe(32)
    store_refresh_token(
        token,
        {
            "sub": user.id,
            "username": user.username,
            "role": user.role,
            "sid": session_id,
        },
    )
    return token


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def revoke_access_token(payload: dict) -> None:
    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp:
        blacklist_jti(jti, float(exp))


def logout_tokens(access_payload: dict | None, refresh_token: str | None) -> None:
    if access_payload:
        revoke_access_token(access_payload)
        user_id = access_payload.get("sub")
        if user_id:
            clear_user_session(user_id)
    if refresh_token:
        revoke_refresh_token(refresh_token)


def is_account_locked(user: User) -> bool:
    if user.locked_until and user.locked_until > _utcnow():
        return True
    if user.locked_until and user.locked_until <= _utcnow():
        user.locked_until = None
        user.failed_login_attempts = 0
    return False


def record_failed_login(db: Session, user: User | None, username: str) -> str | None:
    if user is None:
        return None
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= settings.login_max_attempts:
        user.locked_until = _utcnow() + timedelta(
            minutes=settings.login_lockout_minutes
        )
        user.updated_at = _utcnow()
        db.commit()
        return f"账户已锁定 {settings.login_lockout_minutes} 分钟，请稍后再试"
    user.updated_at = _utcnow()
    db.commit()
    remaining = settings.login_max_attempts - user.failed_login_attempts
    return f"用户名或密码错误，还可尝试 {remaining} 次"


def clear_failed_login(db: Session, user: User) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
    user.updated_at = _utcnow()
    db.commit()


def _set_user_departments(
    db: Session, user: User, department_ids: list[str] | None
) -> None:
    if department_ids is None:
        return
    valid_ids = {
        row[0]
        for row in db.query(Department.id)
        .filter(Department.id.in_(department_ids))
        .all()
    }
    if len(valid_ids) != len(set(department_ids)):
        raise AuthError("存在无效的部门")
    db.query(UserDepartment).filter(UserDepartment.user_id == user.id).delete()
    for dept_id in department_ids:
        db.add(UserDepartment(user_id=user.id, department_id=dept_id))


def register_user(
    db: Session,
    username: str,
    password: str,
    role: str = "user",
    *,
    by_admin: bool = False,
    department_ids: list[str] | None = None,
) -> User:
    if not by_admin and not settings.registration_enabled:
        raise AuthError("系统未开放自助注册", 403)
    username_error = validate_username(username)
    if username_error:
        raise AuthError(username_error)
    policy_error = validate_password(password)
    if policy_error:
        raise AuthError(policy_error)
    if db.query(User).filter(User.username == username).first():
        raise AuthError("用户名已存在")
    user = User(
        id=str(uuid.uuid4()),
        username=username.strip(),
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    _set_user_departments(db, user, department_ids or [])
    db.commit()
    db.refresh(user)
    return user


def change_password(
    db: Session, user: User, old_password: str, new_password: str
) -> None:
    if not verify_password(old_password, user.password_hash):
        raise AuthError("原密码错误", 400)
    policy_error = validate_password(new_password)
    if policy_error:
        raise AuthError(policy_error)
    user.password_hash = hash_password(new_password)
    user.updated_at = _utcnow()
    db.commit()
    invalidate_user_sessions(user.id)


def admin_create_user(
    db: Session,
    username: str,
    password: str,
    role: str,
    department_ids: list[str] | None = None,
) -> User:
    if role not in {"admin", "user"}:
        raise AuthError("无效角色")
    return register_user(
        db,
        username,
        password,
        role=role,
        by_admin=True,
        department_ids=department_ids,
    )


def admin_update_user(
    db: Session,
    user: User,
    *,
    is_active: bool | None = None,
    role: str | None = None,
    department_ids: list[str] | None = None,
) -> User:
    if is_active is not None:
        user.is_active = is_active
        if not is_active:
            invalidate_user_sessions(user.id)
    if role is not None:
        if role not in {"admin", "user"}:
            raise AuthError("无效角色")
        user.role = role
    _set_user_departments(db, user, department_ids)
    user.updated_at = _utcnow()
    db.commit()
    db.refresh(user)
    return user


def admin_reset_password(db: Session, user: User, new_password: str) -> None:
    policy_error = validate_password(new_password)
    if policy_error:
        raise AuthError(policy_error)
    user.password_hash = hash_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    user.updated_at = _utcnow()
    db.commit()
    invalidate_user_sessions(user.id)
