# -*- coding: utf-8 -*-
"""从 User-Agent 解析操作系统、浏览器、设备。"""

from ua_parser import parse as parse_ua


def parse_user_agent(ua: str | None) -> tuple[str | None, str | None, str | None]:
    if not ua or not ua.strip():
        return None, None, None
    try:
        parsed = parse_ua(ua)
        os_name = parsed.os.family or None
        browser = parsed.user_agent.family or None
        device = parsed.device.family or None

        if device in ("Other", "Spider", ""):
            device = None
        if device is None and os_name:
            if os_name in ("Mac OS X", "Windows", "Linux", "Ubuntu", "Chrome OS"):
                device = "Desktop"
            elif os_name in ("Android", "iOS"):
                device = "Mobile"

        return os_name, browser, device
    except Exception:
        return None, None, None
