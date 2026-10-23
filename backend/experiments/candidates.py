"""Persist generated drafts as candidates (deduplicated per challenge)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import orm
from ..generators.base import Draft
from ..generators.dedupe import fingerprint


def save_draft(db: Session, challenge_id: str, d: Draft, *, owner_id: str | None = None, run_id: str | None = None) -> orm.Candidate:
    fp = fingerprint(d.text)
    existing = db.scalar(select(orm.Candidate).where(orm.Candidate.challenge_id == challenge_id,
                                                    orm.Candidate.fingerprint == fp, orm.Candidate.run_id == run_id))
    if existing:
        return existing
    row = orm.Candidate(challenge_id=challenge_id, text=d.text, fingerprint=fp, strategy_id=d.strategy_id, method=d.method,
                        parent_ids=d.parent_ids, generation=d.generation, run_id=run_id, owner_id=owner_id, provenance=d.provenance)
    db.add(row)
    db.flush()
    return row


def candidate_view(c: orm.Candidate) -> dict:
    return {"id": c.id, "challenge_id": c.challenge_id, "text": c.text, "strategy_id": c.strategy_id, "method": c.method,
            "parent_ids": c.parent_ids, "generation": c.generation, "run_id": c.run_id, "owner_id": c.owner_id,
            "saved": c.saved, "tags": c.tags, "provenance": c.provenance, "created_at": c.created_at,
            "token_estimate": max(1, len(c.text) // 4)}
