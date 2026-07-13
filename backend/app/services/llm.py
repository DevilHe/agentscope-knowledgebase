from collections.abc import AsyncIterator

from agentscope.credential import OpenAICredential
from agentscope.message import Msg, UserMsg
from agentscope.model import OpenAIChatModel

from app.config import settings

_MODEL_CACHE: dict[tuple[str, bool], OpenAIChatModel] = {}


def _credential() -> OpenAICredential:
    return OpenAICredential(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def resolve_model_name(scene: str = "chat") -> str:
    """按场景解析模型名；未配置场景专用模型时使用 openai_model。"""
    if scene == "rerank" and settings.openai_model_rerank:
        return settings.openai_model_rerank
    if scene == "chat" and settings.openai_model_chat:
        return settings.openai_model_chat
    if scene == "fallback" and settings.openai_model_fallback:
        return settings.openai_model_fallback
    return settings.openai_model


def get_chat_model(
    *,
    stream: bool = True,
    model_name: str | None = None,
    scene: str = "chat",
) -> OpenAIChatModel:
    name = model_name or resolve_model_name(scene)
    key = (name, stream)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    model = OpenAIChatModel(
        credential=_credential(),
        model=name,
        stream=stream,
        parameters=OpenAIChatModel.Parameters(temperature=0),
    )
    _MODEL_CACHE[key] = model
    return model


def _extract_text(chunk) -> str:
    parts: list[str] = []
    for block in chunk.content or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


async def invoke_text(prompt: str, *, scene: str = "chat") -> str:
    model = get_chat_model(stream=False, scene=scene)
    response = await model([UserMsg(name="user", content=prompt)])
    if hasattr(response, "content"):
        return _extract_text(response)
    return str(response)


async def stream_text(prompt: str, *, scene: str = "chat") -> AsyncIterator[str]:
    model = get_chat_model(stream=True, scene=scene)
    stream_gen = await model([UserMsg(name="user", content=prompt)])
    async for chunk in stream_gen:
        delta = _extract_text(chunk)
        if delta:
            yield delta


async def stream_with_history(
    system_prompt: str,
    history: list[Msg],
    user_prompt: str,
    *,
    scene: str = "chat",
    model_name: str | None = None,
) -> AsyncIterator[str]:
    model = get_chat_model(stream=True, scene=scene, model_name=model_name)
    messages: list[Msg] = []
    if system_prompt:
        messages.append(Msg(name="system", content=system_prompt, role="system"))
    messages.extend(history)
    messages.append(UserMsg(name="user", content=user_prompt))
    stream_gen = await model(messages)
    async for chunk in stream_gen:
        delta = _extract_text(chunk)
        if delta:
            yield delta
