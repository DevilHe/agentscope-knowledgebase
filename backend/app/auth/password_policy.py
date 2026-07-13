import re

from app.config import settings


def _allowed_special_pattern() -> str:
    return re.escape(settings.password_allowed_special)


def validate_password(password: str) -> str | None:
    """校验密码策略，通过返回 None，失败返回错误信息。"""
    special = settings.password_allowed_special
    if len(password) < settings.password_min_length:
        return f"密码长度至少 {settings.password_min_length} 位"
    if len(password) > settings.password_max_length:
        return f"密码长度不能超过 {settings.password_max_length} 位"

    allowed = re.compile(rf"^[A-Za-z0-9{_allowed_special_pattern()}]+$")
    if not allowed.match(password):
        return f"密码只能包含字母、数字和特殊字符（{special}）"

    categories = 0
    if re.search(r"[A-Z]", password):
        categories += 1
    if re.search(r"[a-z]", password):
        categories += 1
    if re.search(r"\d", password):
        categories += 1
    if any(ch in special for ch in password):
        categories += 1
    if categories < 3:
        return "密码需包含大小写、数字、特殊字符中的至少三种"
    return None
