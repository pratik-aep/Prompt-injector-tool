"""Mode 1: deterministic template generation."""
from __future__ import annotations

from typing import Any

from ..database import orm
from ..strategies.library import render_strategy, templates_of
from .base import Draft


def applicable(strategies: list[orm.Strategy], challenge_type: str, ids: list[str] | None) -> list[orm.Strategy]:
    out = [s for s in strategies if (not ids or s.id in ids) and (not s.challenge_types or challenge_type in s.challenge_types)]
    return sorted(out, key=lambda s: s.id)


def public_variables(challenge: dict[str, Any]) -> dict[str, Any]:
    pv = dict((challenge.get("scoring") or {}).get("public_vars") or {})
    pv.setdefault("goal", challenge.get("objective", "").rstrip(".").lower() or "complete the stated objective")
    return pv


def generate_from_templates(strategies: list[orm.Strategy], challenge: dict[str, Any], *, ids: list[str] | None = None,
                            max_len: int | None = None, goal_override: str | None = None) -> list[Draft]:
    """Round-robin across strategies so early picks span different techniques."""
    variables = public_variables(challenge)
    if goal_override:
        variables["goal"] = goal_override
    strats = applicable(strategies, challenge["type"], ids)
    drafts: list[Draft] = []
    depth = max((len(templates_of(s)) for s in strats), default=0)
    for v in range(depth):
        for s in strats:
            if v >= len(templates_of(s)):
                continue
            text = render_strategy(s, variables, v)
            if max_len and len(text) > max_len:
                continue
            drafts.append(Draft(text, "template", s.id, provenance={"variant": v, "category": s.category}))
    return drafts
