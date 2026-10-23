"""Experiment queries, annotation, comparison."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.errors import NotFound
from ..database import orm


def experiment_view(e: orm.Experiment, r: orm.Response | None, ev: orm.Evaluation | None, *, full: bool = True) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": e.id, "challenge_id": e.challenge_id, "candidate_id": e.candidate_id, "target_id": e.target_id,
        "owner_id": e.owner_id, "run_id": e.run_id, "session_id": e.session_id, "mode": e.mode,
        "strategy_id": e.strategy_id, "trial_index": e.trial_index, "tags": e.tags, "notes": e.notes, "created_at": e.created_at,
        "prompt_text": e.prompt_text if full else e.prompt_text[:240],
        "verdict": ev.verdict if ev else None, "score": ev.score if ev else None, "is_estimate": ev.is_estimate if ev else None,
        "latency_ms": r.latency_ms if r else None, "tokens_in": r.tokens_in if r else None, "tokens_out": r.tokens_out if r else None,
        "error": r.error if r else None,
    }
    if full:
        d.update(response_text=r.text if r else None, reasons=ev.reasons if ev else [], checks=(ev.details or {}).get("checks", []) if ev else [],
                 response_meta=r.meta if r else {})
    return d


def list_experiments(db: Session, *, challenge_id: str | None = None, owner_id: str | None = None, verdict: str | None = None,
                     strategy_id: str | None = None, mode: str | None = None, run_id: str | None = None, q: str | None = None,
                     tag: str | None = None, target_id: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    stmt = (select(orm.Experiment, orm.Response, orm.Evaluation)
            .outerjoin(orm.Response, orm.Response.experiment_id == orm.Experiment.id)
            .outerjoin(orm.Evaluation, orm.Evaluation.experiment_id == orm.Experiment.id))
    conds = []
    for col, val in ((orm.Experiment.challenge_id, challenge_id), (orm.Experiment.owner_id, owner_id), (orm.Evaluation.verdict, verdict),
                     (orm.Experiment.strategy_id, strategy_id), (orm.Experiment.mode, mode), (orm.Experiment.run_id, run_id),
                     (orm.Experiment.target_id, target_id)):
        if val:
            conds.append(col == val)
    if q:
        like = f"%{q}%"
        conds.append(or_(orm.Experiment.prompt_text.ilike(like), orm.Response.text.ilike(like), orm.Experiment.notes.ilike(like)))
    if tag:
        conds.append(orm.Experiment.tags.like(f'%"{tag}"%'))
    if conds:
        stmt = stmt.where(*conds)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(orm.Experiment.created_at.desc(), orm.Experiment.id).limit(min(limit, 200)).offset(offset)).all()
    return {"total": total, "limit": limit, "offset": offset, "items": [experiment_view(e, r, v, full=False) for e, r, v in rows]}


def get_experiment(db: Session, eid: str) -> dict[str, Any]:
    e = db.get(orm.Experiment, eid)
    if e is None:
        raise NotFound("Experiment not found")
    r = db.scalar(select(orm.Response).where(orm.Response.experiment_id == eid))
    v = db.scalar(select(orm.Evaluation).where(orm.Evaluation.experiment_id == eid))
    return experiment_view(e, r, v)


def annotate(db: Session, eid: str, *, notes: str | None = None, tags: list[str] | None = None, owner_id: str | None = None) -> dict[str, Any]:
    e = db.get(orm.Experiment, eid)
    if e is None:
        raise NotFound("Experiment not found")
    if notes is not None:
        e.notes = notes
    if tags is not None:
        e.tags = sorted({t.strip() for t in tags if t.strip()})
    if owner_id is not None:
        e.owner_id = owner_id or None
    db.flush()
    return get_experiment(db, eid)


def compare(db: Session, ids: list[str]) -> list[dict[str, Any]]:
    return [get_experiment(db, i) for i in ids]


def find_duplicates(db: Session, challenge_id: str) -> list[dict[str, Any]]:
    rows = db.execute(select(orm.Experiment.prompt_fingerprint, func.count(), func.group_concat(orm.Experiment.id))
                      .where(orm.Experiment.challenge_id == challenge_id).group_by(orm.Experiment.prompt_fingerprint)
                      .having(func.count() > 1)).all()
    return [{"fingerprint": fp, "count": n, "experiment_ids": ids.split(",")} for fp, n, ids in rows]
