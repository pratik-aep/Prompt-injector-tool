"""Manual target: a human relays prompts and pastes responses back."""
from __future__ import annotations

from .base import Message, Target, TargetResponse


class ManualTarget(Target):
    kind = "manual"
    interactive = False

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    async def generate(self, messages: list[Message], *, timeout: float | None = None) -> TargetResponse:
        return TargetResponse(error="Manual target: submit the prompt yourself and paste the response into PromptForge")

    async def health(self):
        return {"ok": True, "detail": "manual mode needs no connection"}
