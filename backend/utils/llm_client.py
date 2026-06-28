"""Small async LLM client shared by PaperHunter services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from ..config import settings


@dataclass
class LLMConfig:
    api_type: str
    api_key: str
    base_url: str
    model: str


def current_llm_config() -> LLMConfig:
    return LLMConfig(
        api_type=(settings.llm_api_type or "anthropic").lower(),
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )


def llm_model_for_crewai() -> str:
    api_type = (settings.llm_api_type or "anthropic").lower()
    if api_type == "openai":
        return f"openai/{settings.llm_model}"
    return f"anthropic/{settings.llm_model}"


def _endpoint(config: LLMConfig) -> str:
    base = config.base_url.rstrip("/")
    if config.api_type == "openai":
        return f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
    return f"{base}/v1/messages" if not base.endswith("/v1/messages") else base


def _headers(config: LLMConfig) -> dict[str, str]:
    if config.api_type == "openai":
        return {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
    return {
        "x-api-key": config.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


async def call_llm(
    messages: list[dict[str, str]],
    *,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
    timeout: int = 30,
    config: LLMConfig | None = None,
) -> str:
    """Call the configured LLM and return plain text."""
    config = config or current_llm_config()
    api_type = config.api_type.lower()

    if api_type == "openai":
        body_messages: list[dict[str, str]] = []
        if system:
            body_messages.append({"role": "system", "content": system})
        body_messages.extend(messages)
        body: dict[str, Any] = {
            "model": config.model,
            "messages": body_messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            body["temperature"] = temperature
    else:
        body = {
            "model": config.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            body["system"] = system
        if temperature is not None:
            body["temperature"] = temperature

    async with aiohttp.ClientSession() as session:
        async with session.post(
            _endpoint(config),
            json=body,
            headers=_headers(config),
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"LLM API error {resp.status}: {error_text[:500]}")
            data = await resp.json()

    if api_type == "openai":
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        return content if isinstance(content, str) else str(content)

    content = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            content += block.get("text", "")
    return content


async def test_llm_connection(config: LLMConfig | None = None) -> dict[str, Any]:
    config = config or current_llm_config()
    text = await call_llm(
        [{"role": "user", "content": "Reply with exactly: PaperHunter OK"}],
        system="You are a connection test endpoint.",
        max_tokens=32,
        temperature=0,
        timeout=20,
        config=config,
    )
    return {
        "ok": True,
        "api_type": config.api_type,
        "model": config.model,
        "base_url": config.base_url,
        "response": text.strip(),
    }
