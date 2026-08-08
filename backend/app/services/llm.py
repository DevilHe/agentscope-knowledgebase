"""LLM 封装：OpenAI 兼容 Chat（LangChain ChatOpenAI）。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any, cast

from langchain_core.messages import (
    AIMessageChunk,
    BaseMessageChunk,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models import base as openai_chat_base

from app.config import settings

_MODEL_CACHE: dict[tuple[str, bool, str], ChatOpenAI] = {}

# ChatOpenAI 官方实现会丢弃第三方字段 reasoning_content；补回以便流式思考展示。
_orig_convert_delta = openai_chat_base._convert_delta_to_message_chunk


def _convert_delta_to_message_chunk_with_reasoning(
    _dict: Mapping[str, Any], default_class: type[BaseMessageChunk]
) -> BaseMessageChunk:
    chunk = _orig_convert_delta(_dict, default_class)
    reasoning = _dict.get("reasoning_content")
    if not reasoning or not isinstance(chunk, AIMessageChunk):
        return chunk
    additional_kwargs = dict(chunk.additional_kwargs or {})
    additional_kwargs["reasoning_content"] = reasoning
    return cast(
        AIMessageChunk,
        chunk.model_copy(update={"additional_kwargs": additional_kwargs}),
    )


openai_chat_base._convert_delta_to_message_chunk = (
    _convert_delta_to_message_chunk_with_reasoning
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


def resolve_llm_credentials(
    *,
    scene: str = "chat",
    model_name: str | None = None,
) -> tuple[str, str, str]:
    """返回 (model_name, api_key, base_url)。

    当 scene 为 fallback，或模型名等于备用模型时，使用备用网关。
    """
    name = model_name or resolve_model_name(scene)
    use_fallback = scene == "fallback" or (
        bool(settings.openai_model_fallback)
        and name == settings.openai_model_fallback
    )
    if use_fallback and (
        settings.openai_api_key_fallback or settings.openai_base_url_fallback
    ):
        return (
            name,
            settings.openai_api_key_fallback or settings.openai_api_key,
            settings.openai_base_url_fallback or settings.openai_base_url,
        )
    return name, settings.openai_api_key, settings.openai_base_url


def get_chat_model(
    *,
    stream: bool = True,
    model_name: str | None = None,
    scene: str = "chat",
) -> ChatOpenAI:
    name, api_key, base_url = resolve_llm_credentials(
        scene=scene, model_name=model_name
    )
    key = (name, stream, base_url)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    model = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
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
