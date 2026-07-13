from contextvars import ContextVar

_user_id: ContextVar[str | None] = ContextVar("audit_user_id", default=None)
_username: ContextVar[str | None] = ContextVar("audit_username", default=None)
_ip: ContextVar[str | None] = ContextVar("audit_ip", default=None)
_user_agent: ContextVar[str | None] = ContextVar("audit_user_agent", default=None)


def set_audit_context(
    *,
    user_id: str,
    username: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    _user_id.set(user_id)
    _username.set(username)
    _ip.set(ip)
    _user_agent.set(user_agent)


def get_audit_context() -> dict[str, str | None]:
    return {
        "user_id": _user_id.get(),
        "username": _username.get(),
        "ip": _ip.get(),
        "user_agent": _user_agent.get(),
    }
