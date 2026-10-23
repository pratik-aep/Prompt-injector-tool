"""Local Ollama adapter (streaming, cancellable, concurrency-limited)."""
from __future__ import annotations

import json
import shutil
import time
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.security import redact
from .base import MAX_RESPONSE_CHARS, Message, Target, TargetResponse, local_inference_slot


async def detect_ollama(base_url: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    """Report whether Ollama is installed, whether its server answers, and models."""
    base = (base_url or get_settings().ollama_url).rstrip("/")
    info: dict[str, Any] = {
        "installed": shutil.which("ollama") is not None,
        "server_up": False, "url": base, "models": [], "error": None,
    }
    try:
        async with httpx.AsyncClient(timeout=3.0, transport=transport) as c:
            r = await c.get(f"{base}/api/tags")
            r.raise_for_status()
            info["server_up"] = True
            info["models"] = [
                {
                    "name": m.get("name"), "size_bytes": m.get("size"),
                    "family": (m.get("details") or {}).get("family"),
                    "parameter_size": (m.get("details") or {}).get("parameter_size"),
                    "quantization": (m.get("details") or {}).get("quantization_level"),
                    "modified_at": m.get("modified_at"),
                }
                for m in r.json().get("models", [])
            ]
    except (httpx.HTTPError, ValueError) as e:
        info["error"] = redact(f"Ollama server not reachable: {type(e).__name__}")
    return info


class OllamaTarget(Target):
    kind = "ollama"

    def __init__(self, config: dict[str, Any], transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport
        self.model: str = config.get("model", "")
        self.base_url = (config.get("base_url") or get_settings().ollama_url).rstrip("/")
        self.options: dict[str, Any] = {
            "temperature": config.get("temperature", 0.7),
            "num_predict": config.get("max_tokens", 512),
        }
        if config.get("seed") is not None:
            self.options["seed"] = config["seed"]
        self.keep_alive = config.get("keep_alive", "5m")
        self.timeout = float(config.get("timeout_s", get_settings().default_timeout_s))
        self.think = config.get("think")  # None => model default; False disables reasoning on capable models

    async def health(self) -> dict[str, Any]:
        info = await detect_ollama(self.base_url, self.transport)
        names = {m["name"] for m in info["models"]}
        ready = info["server_up"] and (self.model in names or f"{self.model}:latest" in names)
        return {"ok": ready, "installed": info["installed"], "server_up": info["server_up"],
                "model_present": ready, "detail": info["error"] or ("ready" if ready else f"model '{self.model}' not installed")}

    async def generate(self, messages: list[Message], *, timeout: float | None = None) -> TargetResponse:
        if not self.model:
            return TargetResponse(error="No Ollama model selected")
        payload: dict[str, Any] = {
            "model": self.model, "messages": [m.to_dict() for m in messages],
            "stream": True, "options": self.options, "keep_alive": self.keep_alive,
        }
        if self.think is not None:
            payload["think"] = self.think
        t0 = time.perf_counter()
        chunks: list[str] = []
        total = 0
        meta: dict[str, Any] = {}
        tin = tout = None
        sem = local_inference_slot(get_settings().local_concurrency)
        try:
            async with sem:
                limits = httpx.Timeout(timeout or self.timeout, connect=5.0)
                async with httpx.AsyncClient(timeout=limits, transport=self.transport) as c:
                    async with c.stream("POST", f"{self.base_url}/api/chat", json=payload) as r:
                        if r.status_code >= 400:
                            body = (await r.aread()).decode("utf-8", "replace")[:300]
                            return TargetResponse(error=redact(f"Ollama HTTP {r.status_code}: {body}"),
                                                  latency_ms=(time.perf_counter() - t0) * 1000)
                        async for line in r.aiter_lines():
                            if not line.strip():
                                continue
                            data = json.loads(line)
                            if "error" in data:
                                return TargetResponse(error=redact(f"Ollama error: {data['error']}"),
                                                      latency_ms=(time.perf_counter() - t0) * 1000)
                            piece = (data.get("message") or {}).get("content", "")
                            if piece and total < MAX_RESPONSE_CHARS:
                                chunks.append(piece)
                                total += len(piece)
                            if data.get("done"):
                                tin, tout = data.get("prompt_eval_count"), data.get("eval_count")
                                meta = {"total_duration_ns": data.get("total_duration"),
                                        "done_reason": data.get("done_reason")}
        except httpx.TimeoutException:
            return TargetResponse(error="Ollama request timed out", latency_ms=(time.perf_counter() - t0) * 1000)
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            return TargetResponse(error=redact(f"Ollama connection failure: {type(e).__name__}"),
                                  latency_ms=(time.perf_counter() - t0) * 1000)
        text = "".join(chunks)[:MAX_RESPONSE_CHARS]
        meta["truncated"] = total >= MAX_RESPONSE_CHARS
        return TargetResponse(text=text, latency_ms=(time.perf_counter() - t0) * 1000,
                              tokens_in=tin, tokens_out=tout, meta=meta)
