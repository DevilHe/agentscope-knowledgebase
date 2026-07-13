"""兼容导出；实际 Prompt 由 prompt_registry 按版本加载。"""

from app.core.prompt_registry import resolve_system_prompt

UNIFIED_AGENT_SYSTEM_PROMPT, _DEFAULT_PROMPT_VERSION = resolve_system_prompt(None)
