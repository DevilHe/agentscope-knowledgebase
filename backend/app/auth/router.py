from pydantic import BaseModel, Field

from app.utils.datetime_ser import to_utc_iso

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.deps import (
    get_client_ip,
    get_current_user,
    get_optional_token_payload,
    require_admin,
)
from app.auth.password_crypto import PasswordDecryptError, decrypt_password
from app.auth.service import (
    AuthError,
    admin_create_user,
    admin_reset_password,
    admin_update_user,
    authenticate_user,
    change_password,
    clear_failed_login,
    create_access_token,
    create_refresh_token,
    is_account_locked,
    logout_tokens,
    record_failed_login,
    register_user,
)
from app.auth.captcha import captcha_json_response, create_captcha, verify_captcha
from app.auth.token_store import (
    check_rate_limit,
    get_refresh_token,
    invalidate_user_sessions,
    revoke_refresh_token,
    start_user_session,
    validate_user_session,
)
from app.config import settings
from app.db.models import Department, User, UserDepartment, get_db
from app.services.acl import list_accessible_knowledge_bases

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)
    captcha_id: str = Field(min_length=1)
    captcha_answer: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    username: str
    role: str
    department_names: list[str] = []


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class RegisterRequest(BaseModel):
    username: str = Field(min_length=4, max_length=16)
    password: str = Field(min_length=1)
    captcha_id: str = Field(min_length=1)
    captcha_answer: str = Field(min_length=1)
    department_id: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=4, max_length=16)
    password: str = Field(min_length=1)
    role: str = Field(default="user")
    department_ids: list[str] = Field(default_factory=list)


class AdminUpdateUserRequest(BaseModel):
    is_active: bool | None = None
    role: str | None = None
    department_ids: list[str] | None = None


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=1)


class MeResponse(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool
    departments: list[dict]
    knowledge_bases: list[dict]


class UserItem(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool
    failed_login_attempts: int
    locked_until: str | None
    created_at: str | None
    department_ids: list[str] = []
    department_names: list[str] = []


class CaptchaResponse(BaseModel):
    captcha_id: str
    image: str


def _renew_tokens(user: User, db: Session, session_id: str) -> TokenResponse:
    access_token, _, _ = create_access_token(user, session_id)
    refresh_token = create_refresh_token(user, session_id)
    _, dept_names = _user_departments(db, user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        username=user.username,
        role=user.role,
        department_names=dept_names,
    )


def _issue_tokens(user: User, db: Session) -> TokenResponse:
    invalidate_user_sessions(user.id)
    session_id = start_user_session(user.id)
    return _renew_tokens(user, db, session_id)


def _handle_auth_error(exc: AuthError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def _resolve_password(encrypted: str) -> str:
    try:
        return decrypt_password(encrypted)
    except PasswordDecryptError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码解密失败，请刷新页面后重试",
        ) from exc


@router.get("/captcha", response_model=CaptchaResponse)
def get_captcha():
    captcha_id, image = create_captcha()
    return captcha_json_response(captcha_id, image)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = get_client_ip(request)
    if not check_rate_limit(
        f"login:{ip}",
        settings.login_rate_limit_per_ip,
        settings.login_rate_limit_window_seconds,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录过于频繁，请稍后再试",
        )

    if not verify_captcha(body.captcha_id, body.captcha_answer):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已过期"
        )

    user = db.query(User).filter(User.username == body.username).first()
    if user and not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已禁用")

    if user and is_account_locked(user):
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED, detail="账户已锁定，请稍后再试"
        )

    authenticated = authenticate_user(
        db, body.username, _resolve_password(body.password)
    )
    if not authenticated:
        hint = record_failed_login(db, user, body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=hint or "用户名或密码错误",
        )

    clear_failed_login(db, authenticated)
    return _issue_tokens(authenticated, db)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    data = get_refresh_token(body.refresh_token)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌无效或已过期"
        )

    user = db.get(User, data.get("sub"))
    if not user or not user.is_active:
        revoke_refresh_token(body.refresh_token)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用"
        )

    session_id = data.get("sid")
    ok, err = validate_user_session(user.id, session_id)
    if not ok:
        revoke_refresh_token(body.refresh_token)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err or "会话已失效，请重新登录",
        )

    revoke_refresh_token(body.refresh_token)
    return _renew_tokens(user, db, session_id)


@router.post("/logout", status_code=204)
def logout(
    body: LogoutRequest,
    payload: dict | None = Depends(get_optional_token_payload),
):
    logout_tokens(payload, body.refresh_token)
    return None


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if not verify_captcha(body.captcha_id, body.captcha_answer):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已过期"
        )
    try:
        user = register_user(
            db,
            body.username,
            _resolve_password(body.password),
            department_ids=[body.department_id],
        )
    except AuthError as exc:
        _handle_auth_error(exc)
    return _issue_tokens(user, db)


def _user_departments(db: Session, user_id: str) -> tuple[list[str], list[str]]:
    rows = (
        db.query(UserDepartment, Department)
        .join(Department, Department.id == UserDepartment.department_id)
        .filter(UserDepartment.user_id == user_id)
        .all()
    )
    ids = [dept.id for _, dept in rows]
    names = [dept.name for _, dept in rows]
    return ids, names


def _serialize_user_item(db: Session, user: User) -> UserItem:
    dept_ids, dept_names = _user_departments(db, user.id)
    return UserItem(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        failed_login_attempts=user.failed_login_attempts,
        locked_until=to_utc_iso(user.locked_until),
        created_at=to_utc_iso(user.created_at),
        department_ids=dept_ids,
        department_names=dept_names,
    )


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dept_ids, dept_names = _user_departments(db, user.id)
    departments = [
        {"id": dept_id, "name": dept_name}
        for dept_id, dept_name in zip(dept_ids, dept_names, strict=False)
    ]
    knowledge_bases = [
        {
            "id": item.id,
            "slug": item.slug,
            "name": item.name,
            "department_id": item.department_id,
            "department_name": item.department_name,
        }
        for item in list_accessible_knowledge_bases(db, user)
    ]
    return MeResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        departments=departments,
        knowledge_bases=knowledge_bases,
    )


@router.post("/change-password", status_code=204)
def change_password_api(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        change_password(
            db,
            user,
            _resolve_password(body.old_password),
            _resolve_password(body.new_password),
        )
    except AuthError as exc:
        _handle_auth_error(exc)
    return None


@router.get("/users", response_model=list[UserItem])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(User).order_by(User.created_at.desc()).all()
    return [_serialize_user_item(db, u) for u in rows]


@router.post("/users", response_model=UserItem, status_code=201)
def create_user(
    body: AdminCreateUserRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        user = admin_create_user(
            db,
            body.username,
            _resolve_password(body.password),
            body.role,
            department_ids=body.department_ids,
        )
    except AuthError as exc:
        _handle_auth_error(exc)
    return _serialize_user_item(db, user)


@router.patch("/users/{user_id}", response_model=UserItem)
def update_user(
    user_id: str,
    body: AdminUpdateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id and body.is_active is False:
        raise HTTPException(status_code=400, detail="不能禁用当前登录账户")
    try:
        user = admin_update_user(
            db,
            user,
            is_active=body.is_active,
            role=body.role,
            department_ids=body.department_ids,
        )
    except AuthError as exc:
        _handle_auth_error(exc)
    return _serialize_user_item(db, user)


@router.post("/users/{user_id}/reset-password", status_code=204)
def reset_user_password(
    user_id: str,
    body: AdminResetPasswordRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    try:
        admin_reset_password(db, user, _resolve_password(body.new_password))
    except AuthError as exc:
        _handle_auth_error(exc)
    return None
