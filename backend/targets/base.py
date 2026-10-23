"""Provider-independent target interface."""
from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant"]

MAX_RESPONSE_CHARS = 20_000  # memory-conscious cap on stored/streamed output


@dataclass
class Message:
    """A chat message. ``role`` is a real API role, never inferred from text.

    Text such as ``"SYSTEM: ..."`` inside a user message is just user text.
    Only trusted challenge configuration may produce ``system`` messages.
    """
    role: Role
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class TargetResponse:
    text: str = ""
    latency_ms: float = 0.0
    tokens_in: int | None = None
    tokens_out: int | None = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


def estimate_tokens(text: str) -> int:
    """Cheap, provider-agnostic estimate (~4 chars/token)."""
    return max(1, (len(text) + 3) // 4) if text else 0


class Target(abc.ABC):
    kind: str = "abstract"
    interactive = True  # False => needs a human in the loop (manual mode)

    @abc.abstractmethod
    async def generate(self, messages: list[Message], *, timeout: float | None = None) -> TargetResponse:
        """Send ``messages`` and return the full response. Must not raise on
        ordinary provider failures — return ``TargetResponse(error=...)``.
        Task cancellation (``asyncio.CancelledError``) must propagate."""

    async def health(self) -> dict[str, Any]:
        return {"ok": True, "detail": "no health check for this target kind"}


# Prevents unbounded concurrent local inference (default: 1 at a time).
_local_semaphore: asyncio.Semaphore | None = None
_local_limit = 0


def local_inference_slot(limit: int) -> asyncio.Semaphore:
    global _local_semaphore, _local_limit
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover
        loop = None
    if _local_semaphore is None or _local_limit != limit or getattr(_local_semaphore, "_pf_loop", None) is not loop:
        _local_semaphore = asyncio.Semaphore(max(1, limit))
        _local_semaphore._pf_loop = loop  # type: ignore[attr-defined]
        _local_limit = limit
    return _local_semaphore
