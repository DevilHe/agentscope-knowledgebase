"""LLM 封装：OpenAI 兼容 Chat（LangChain ChatOpenAI）。"""

from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings

_MODEL_CACHE: dict[tuple[str, bool], ChatOpenAI] = {}


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
) -> ChatOpenAI:
    name = model_name or resolve_model_name(scene)
    key = (name, stream)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    model = ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=name,
        temperature=0,
        streaming=stream,
    )
    _MODEL_CACHE[key] = model
    return model


async def invoke_text(prompt: str, *, scene: str = "chat") -> str:
    model = get_chat_model(stream=False, scene=scene)
    response = await model.ainvoke([HumanMessage(content=prompt)])
    content = response.content
    if isinstance(content, str):
        return content
    return str(content)


async def stream_text(prompt: str, *, scene: str = "chat") -> AsyncIterator[str]:
    model = get_chat_model(stream=True, scene=scene)
    async for chunk in model.astream([HumanMessage(content=prompt)]):
        delta = chunk.content
        if isinstance(delta, str) and delta:
            yield delta


async def stream_with_history(
    system_prompt: str,
    history: list,
    user_prompt: str,
    *,
    scene: str = "chat",
    model_name: str | None = None,
) -> AsyncIterator[str]:
    model = get_chat_model(stream=True, scene=scene, model_name=model_name)
    messages: list = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.extend(history)
    messages.append(HumanMessage(content=user_prompt))
    async for chunk in model.astream(messages):
        delta = chunk.content
        if isinstance(delta, str) and delta:
            yield delta
