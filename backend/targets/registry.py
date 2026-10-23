"""Build runtime Target objects from stored rows, enforcing scope rules."""
from __future__ import annotations

from typing import Any

from ..core.errors import ScopeViolation, ValidationFailed
from ..core.security import validate_url
from ..database import orm
from .base import Target
from .http_api import HttpApiTarget, validate_http_config
from .manual import ManualTarget
from .ollama import OllamaTarget
from .providers import AnthropicTarget, OpenAITarget
from .simulated import SimulatedTarget

KINDS = ("ollama", "http_api", "manual", "openai", "anthropic", "simulated")
REMOTE_KINDS = ("http_api", "openai", "anthropic")


def validate_target_config(kind: str, config: dict[str, Any], allow_private: bool) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValidationFailed(f"Unknown target kind '{kind}'. Valid: {', '.join(KINDS)}")
    if kind == "http_api":
        return validate_http_config(config, allow_private=allow_private)
    if kind == "ollama":
        if not config.get("model"):
            raise ValidationFailed("Ollama target requires a 'model'")
        if config.get("base_url"):
            validate_url(config["base_url"], allow_private=True)  # Ollama is local by design
    if kind in ("openai", "anthropic") and not config.get("model"):
        raise ValidationFailed(f"{kind} target requires a 'model'")
    return config


def build_target(row: orm.Target, *, transport=None) -> Target:
    """Instantiate a target. Disabled targets are never contacted."""
    if not row.enabled:
        raise ScopeViolation(f"Target '{row.name}' is disabled; enable it explicitly before testing")
    cfg = row.config or {}
    if row.kind == "ollama":
        return OllamaTarget(cfg, transport=transport)
    if row.kind == "http_api":
        return HttpApiTarget(cfg, target_id=row.id, secret_ref=row.secret_ref, allow_private=row.allow_private, transport=transport)
    if row.kind == "manual":
        return ManualTarget(cfg)
    if row.kind == "openai":
        return OpenAITarget(cfg, secret_ref=row.secret_ref, transport=transport)
    if row.kind == "anthropic":
        return AnthropicTarget(cfg, secret_ref=row.secret_ref, transport=transport)
    if row.kind == "simulated":
        return SimulatedTarget(cfg)
    raise ValidationFailed(f"Unknown target kind '{row.kind}'")
