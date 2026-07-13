import re


def validate_username(username: str) -> str | None:
    """校验用户名：4-16 位，仅大小写字母或数字。"""
    name = username.strip()
    if len(name) < 4:
        return "用户名至少 4 位"
    if len(name) > 16:
        return "用户名不能超过 16 位"
    if not re.match(r"^[A-Za-z0-9]+$", name):
        return "用户名只能包含大小写字母或数字"
    return None
