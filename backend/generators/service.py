"""Unified candidate generation across all four modes, with dedupe + diversity."""
from __future__ import annotations

from typing import Any

from ..core.errors import ValidationFailed
from ..database import orm
from ..targets.base import Target
from .ai import generate_with_llm
from .base import Draft, GenerationRequest
from .dedupe import dedupe, diverse_subset
from .template import generate_from_templates


async def generate_candidates(req: GenerationRequest, strategies: list[orm.Strategy], *, llm: Target | None = None,
                              existing_texts: list[str] | None = None) -> tuple[list[Draft], list[str]]:
    """Return (drafts, warnings). Never returns near-duplicates of each other or of ``existing_texts``."""
    warnings: list[str] = []
    maxlen = req.challenge.get("max_prompt_length", 1500)
    if req.mode == "manual":
        if not req.manual_text.strip():
            raise ValidationFailed("manual mode requires text")
        if len(req.manual_text) > maxlen:
            raise ValidationFailed(f"Prompt exceeds the challenge limit of {maxlen} characters")
        return [Draft(req.manual_text, "manual")], warnings
    if req.mode not in ("template", "ai", "hybrid"):
        raise ValidationFailed("mode must be template, ai, hybrid or manual")

    drafts: list[Draft] = []
    tmpl: list[Draft] = []
    if req.mode in ("template", "hybrid"):
        tmpl = generate_from_templates(strategies, req.challenge, ids=req.strategy_ids, max_len=maxlen)
        drafts.extend(tmpl)
    if req.mode in ("ai", "hybrid"):
        if llm is None:
            warnings.append("No LLM target available; " + ("using templates only" if tmpl else "no candidates generated"))
        else:
            summaries = [f"{s.name}: {s.description}" for s in strategies
                         if (not req.strategy_ids or s.id in req.strategy_ids) and (not s.challenge_types or req.challenge["type"] in s.challenge_types)]
            seeds = None
            if req.mode == "hybrid" and tmpl:
                idx = diverse_subset([d.text for d in tmpl], min(4, len(tmpl)))
                seeds = [tmpl[i].text for i in idx]
            llm_drafts, err = await generate_with_llm(llm, req, summaries, seeds=seeds, method="ai" if req.mode == "ai" else "hybrid")
            if err:
                warnings.append(f"LLM generation failed: {err}")
            drafts.extend(llm_drafts)
    keep = dedupe([d.text for d in drafts], req.similarity_threshold, existing_texts)
    removed = len(drafts) - len(keep)
    if removed:
        warnings.append(f"Removed {removed} duplicate/near-duplicate candidate(s)")
    drafts = [drafts[i] for i in keep]
    if len(drafts) > req.count:
        # Prefer diversity over generation order, but keep technique spread.
        drafts = [drafts[i] for i in diverse_subset([d.text for d in drafts], req.count)]
    return drafts, warnings
