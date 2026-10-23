"""Optional hosted-provider adapters. Inactive without valid credentials."""
from __future__ import annotations

import time
from typing import Any

import httpx

from ..core.security import redact, resolve_secret
from .base import MAX_RESPONSE_CHARS, Message, Target, TargetResponse


class OpenAITarget(Target):
    kind = "openai"

    def __init__(self, config: dict[str, Any], *, secret_ref: str | None, transport: httpx.AsyncBaseTransport | None = None):
        self.model = config.get("model", "")
        self.base = config.get("base_url", "https://api.openai.com/v1").rstrip("/")
        self.max_tokens = config.get("max_tokens", 512)
        self.temperature = config.get("temperature", 0.7)
        self.timeout = float(config.get("timeout_s", 60))
        self.secret_ref = secret_ref or "env:OPENAI_API_KEY"
        self.transport = transport

    async def health(self) -> dict[str, Any]:
        ok = bool(resolve_secret(self.secret_ref)) and bool(self.model)
        return {"ok": ok, "detail": "credentials found" if ok else "missing API key or model"}

    async def generate(self, messages: list[Message], *, timeout: float | None = None) -> TargetResponse:
        key = resolve_secret(self.secret_ref)
        if not key:
            return TargetResponse(error="OpenAI API key not configured")
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout, transport=self.transport) as c:
                r = await c.post(f"{self.base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                                 json={"model": self.model, "messages": [m.to_dict() for m in messages],
                                       "max_tokens": self.max_tokens, "temperature": self.temperature})
            if r.status_code >= 400:
                return TargetResponse(error=redact(f"OpenAI HTTP {r.status_code}"), latency_ms=(time.perf_counter() - t0) * 1000)
            d = r.json()
            u = d.get("usage", {})
            return TargetResponse(text=(d["choices"][0]["message"]["content"] or "")[:MAX_RESPONSE_CHARS],
                                  latency_ms=(time.perf_counter() - t0) * 1000,
                                  tokens_in=u.get("prompt_tokens"), tokens_out=u.get("completion_tokens"))
        except httpx.TimeoutException:
            return TargetResponse(error="OpenAI request timed out")
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            return TargetResponse(error=redact(f"OpenAI request failed ({type(e).__name__})"))


class AnthropicTarget(Target):
    kind = "anthropic"

    def __init__(self, config: dict[str, Any], *, secret_ref: str | None, transport: httpx.AsyncBaseTransport | None = None):
        self.model = config.get("model", "")
        self.base = config.get("base_url", "https://api.anthropic.com").rstrip("/")
        self.max_tokens = config.get("max_tokens", 512)
        self.temperature = config.get("temperature", 0.7)
        self.timeout = float(config.get("timeout_s", 60))
        self.secret_ref = secret_ref or "env:ANTHROPIC_API_KEY"
        self.transport = transport

    async def health(self) -> dict[str, Any]:
        ok = bool(resolve_secret(self.secret_ref)) and bool(self.model)
        return {"ok": ok, "detail": "credentials found" if ok else "missing API key or model"}

    async def generate(self, messages: list[Message], *, timeout: float | None = None) -> TargetResponse:
        key = resolve_secret(self.secret_ref)
        if not key:
            return TargetResponse(error="Anthropic API key not configured")
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        turns = [m.to_dict() for m in messages if m.role != "system"]
        body: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens,
                                "temperature": self.temperature, "messages": turns}
        if system:
            body["system"] = system
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout, transport=self.transport) as c:
                r = await c.post(f"{self.base}/v1/messages", json=body,
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
            if r.status_code >= 400:
                return TargetResponse(error=redact(f"Anthropic HTTP {r.status_code}"), latency_ms=(time.perf_counter() - t0) * 1000)
            d = r.json()
            text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
            u = d.get("usage", {})
            return TargetResponse(text=text[:MAX_RESPONSE_CHARS], latency_ms=(time.perf_counter() - t0) * 1000,
                                  tokens_in=u.get("input_tokens"), tokens_out=u.get("output_tokens"))
        except httpx.TimeoutException:
            return TargetResponse(error="Anthropic request timed out")
        except (httpx.HTTPError, ValueError) as e:
            return TargetResponse(error=redact(f"Anthropic request failed ({type(e).__name__})"))
