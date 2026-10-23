"""Configurable adapter for competition-provided, explicitly registered endpoints."""
from __future__ import annotations

import asyncio
import copy
import json
import time
from typing import Any

import httpx

from ..core.errors import ValidationFailed
from ..core.security import RateLimiter, redact, resolve_secret, validate_url
from .base import MAX_RESPONSE_CHARS, Message, Target, TargetResponse

_limiters: dict[str, RateLimiter] = {}

DEFAULTS = {
    "method": "POST",
    "auth": {"type": "none"},       # none | bearer | header  (header uses auth.header_name)
    "headers": {},
    "body_template": {"messages": "{{messages}}"},
    "response_path": "choices.0.message.content",
    "timeout_s": 30.0,
    "rate_limit_per_min": 20,
    "retries": 1,
    "retry_backoff_s": 1.0,
}


def validate_http_config(config: dict[str, Any], *, allow_private: bool) -> dict[str, Any]:
    cfg = {**DEFAULTS, **config}
    if not cfg.get("url"):
        raise ValidationFailed("HTTP target requires a 'url'")
    validate_url(cfg["url"], allow_private=allow_private)
    if str(cfg["method"]).upper() not in ("GET", "POST", "PUT", "PATCH"):
        raise ValidationFailed("method must be GET, POST, PUT or PATCH")
    cfg["method"] = str(cfg["method"]).upper()
    if cfg["auth"].get("type") not in ("none", "bearer", "header"):
        raise ValidationFailed("auth.type must be none, bearer or header")
    if not (1 <= float(cfg["timeout_s"]) <= 300):
        raise ValidationFailed("timeout_s must be between 1 and 300")
    if not (1 <= int(cfg["rate_limit_per_min"]) <= 600):
        raise ValidationFailed("rate_limit_per_min must be between 1 and 600")
    if not (0 <= int(cfg["retries"]) <= 5):
        raise ValidationFailed("retries must be between 0 and 5")
    return cfg


def _fill(node: Any, prompt: str, messages: list[dict[str, str]]) -> Any:
    """Substitute {{prompt}} / {{messages}} placeholders in a JSON body template."""
    if isinstance(node, str):
        if node == "{{messages}}":
            return messages
        return node.replace("{{prompt}}", prompt)
    if isinstance(node, list):
        return [_fill(n, prompt, messages) for n in node]
    if isinstance(node, dict):
        return {k: _fill(v, prompt, messages) for k, v in node.items()}
    return node


def extract_path(data: Any, path: str) -> Any:
    """Dotted path lookup supporting list indexes, e.g. ``choices.0.message.content``."""
    cur = data
    for part in filter(None, path.split(".")):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur[part]
        else:
            raise KeyError(part)
    return cur


class HttpApiTarget(Target):
    kind = "http_api"

    def __init__(self, config: dict[str, Any], *, target_id: str, secret_ref: str | None, allow_private: bool = False,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.cfg = validate_http_config(config, allow_private=allow_private)
        self.allow_private = allow_private
        self.secret_ref = secret_ref
        self.transport = transport
        lim = _limiters.get(target_id)
        if lim is None or lim.max_calls != int(self.cfg["rate_limit_per_min"]):
            lim = _limiters[target_id] = RateLimiter(int(self.cfg["rate_limit_per_min"]), 60.0)
        self.limiter = lim

    def _headers(self) -> dict[str, str]:
        h = {str(k): str(v) for k, v in self.cfg["headers"].items()}
        auth = self.cfg["auth"]
        if auth["type"] != "none":
            token = resolve_secret(self.secret_ref)
            if not token:
                raise ValidationFailed("Credential not found: set the environment variable / Keychain item referenced by secret_ref")
            if auth["type"] == "bearer":
                h["Authorization"] = f"Bearer {token}"
            else:
                h[auth.get("header_name", "X-API-Key")] = token
        return h

    async def generate(self, messages: list[Message], *, timeout: float | None = None) -> TargetResponse:
        # Re-validate at call time (DNS may have changed since registration).
        try:
            validate_url(self.cfg["url"], allow_private=self.allow_private)
            headers = self._headers()
        except ValidationFailed as e:
            return TargetResponse(error=str(e))
        except Exception as e:
            return TargetResponse(error=redact(str(e)))
        msgs = [m.to_dict() for m in messages]
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        body = _fill(copy.deepcopy(self.cfg["body_template"]), last_user, msgs)
        attempts = int(self.cfg["retries"]) + 1
        t0 = time.perf_counter()
        last_err = "request failed"
        for i in range(attempts):
            await self.limiter.acquire()
            try:
                async with httpx.AsyncClient(timeout=timeout or float(self.cfg["timeout_s"]),
                                             transport=self.transport, follow_redirects=False) as c:
                    kw: dict[str, Any] = {"headers": headers}
                    if self.cfg["method"] == "GET":
                        kw["params"] = {k: v if isinstance(v, str) else json.dumps(v) for k, v in body.items()}
                    else:
                        kw["json"] = body
                    r = await c.request(self.cfg["method"], self.cfg["url"], **kw)
                if r.status_code in (429, 500, 502, 503, 504) and i < attempts - 1:
                    last_err = f"HTTP {r.status_code}"
                    await asyncio.sleep(float(self.cfg["retry_backoff_s"]) * (2 ** i))
                    continue
                if r.status_code >= 400:
                    return TargetResponse(error=redact(f"HTTP {r.status_code}: {r.text[:200]}"),
                                          latency_ms=(time.perf_counter() - t0) * 1000)
                try:
                    data = r.json()
                    text = extract_path(data, self.cfg["response_path"]) if self.cfg["response_path"] else r.text
                except (ValueError, KeyError, IndexError, TypeError):
                    return TargetResponse(error="Could not parse response using response_path",
                                          latency_ms=(time.perf_counter() - t0) * 1000)
                usage = data.get("usage", {}) if isinstance(data, dict) else {}
                return TargetResponse(text=str(text)[:MAX_RESPONSE_CHARS], latency_ms=(time.perf_counter() - t0) * 1000,
                                      tokens_in=usage.get("prompt_tokens"), tokens_out=usage.get("completion_tokens"),
                                      meta={"status": r.status_code, "attempts": i + 1})
            except httpx.TimeoutException:
                last_err = "request timed out"
            except httpx.HTTPError as e:
                last_err = f"connection failure ({type(e).__name__})"
            if i < attempts - 1:
                await asyncio.sleep(float(self.cfg["retry_backoff_s"]) * (2 ** i))
        return TargetResponse(error=last_err, latency_ms=(time.perf_counter() - t0) * 1000)
