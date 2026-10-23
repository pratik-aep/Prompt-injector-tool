from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Draft:
    """A not-yet-persisted candidate with a record of how it was made."""
    text: str
    method: str                       # template | ai | hybrid | manual | mutation
    strategy_id: str | None = None
    parent_ids: list[str] = field(default_factory=list)
    generation: int = 0
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationRequest:
    challenge: dict[str, Any]                 # PUBLIC challenge view only (no secrets)
    mode: str = "template"                    # template | ai | hybrid | manual
    strategy_ids: list[str] | None = None
    count: int = 6
    previous: list[dict[str, Any]] = field(default_factory=list)   # {text, verdict, score}
    constraints: str = ""
    budget_remaining: int | None = None
    manual_text: str = ""
    similarity_threshold: float = 0.8
