"""JSON/CSV export, JSON import, and database backup. Secrets (evaluator/defender config) are never exported."""
from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.errors import ValidationFailed
from ..database import orm
from .experiments import experiment_view

CSV_COLUMNS = ["id", "created_at", "challenge_id", "owner_id", "mode", "strategy_id", "target_id", "trial_index", "verdict",
               "score", "latency_ms", "tokens_in", "tokens_out", "tags", "notes", "prompt_text", "response_text"]
EXPORT_VERSION = 1


def _rows(db: Session, challenge_id: str | None):
    stmt = (select(orm.Experiment, orm.Response, orm.Evaluation)
            .outerjoin(orm.Response, orm.Response.experiment_id == orm.Experiment.id)
            .outerjoin(orm.Evaluation, orm.Evaluation.experiment_id == orm.Experiment.id).order_by(orm.Experiment.created_at))
    if challenge_id:
        stmt = stmt.where(orm.Experiment.challenge_id == challenge_id)
    return db.execute(stmt).all()


def export_json(db: Session, challenge_id: str | None = None) -> dict[str, Any]:
    exps = [experiment_view(e, r, v) for e, r, v in _rows(db, challenge_id)]
    cq = select(orm.Candidate)
    if challenge_id:
        cq = cq.where(orm.Candidate.challenge_id == challenge_id)
    return {
        "promptforge_export": EXPORT_VERSION, "exported_at": datetime.now().isoformat(timespec="seconds"),
        "members": [{"id": m.id, "name": m.name, "role": m.role} for m in db.scalars(select(orm.TeamMember))],
        "candidates": [{"id": c.id, "challenge_id": c.challenge_id, "text": c.text, "strategy_id": c.strategy_id, "method": c.method,
                        "parent_ids": c.parent_ids, "generation": c.generation, "saved": c.saved, "tags": c.tags, "provenance": c.provenance}
                       for c in db.scalars(cq)],
        "experiments": exps,
        "verified_flags": [{"challenge_id": f.challenge_id, "flag": f.flag, "experiment_id": f.experiment_id, "source": f.source}
                           for f in db.scalars(select(orm.VerifiedFlag))],
    }


def export_csv(db: Session, challenge_id: str | None = None) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for e, r, v in _rows(db, challenge_id):
        d = experiment_view(e, r, v)
        d["tags"] = ";".join(d["tags"] or [])
        # Neutralise spreadsheet formula injection from untrusted prompt/response text.
        for k in ("prompt_text", "response_text", "notes"):
            if isinstance(d.get(k), str) and d[k][:1] in ("=", "+", "-", "@"):
                d[k] = "'" + d[k]
        w.writerow(d)
    return buf.getvalue()


def import_json(db: Session, data: dict[str, Any]) -> dict[str, int]:
    """Merge a teammate's export. Existing ids are skipped; experiments for unknown challenges are rejected."""
    if data.get("promptforge_export") != EXPORT_VERSION:
        raise ValidationFailed("Not a PromptForge export (or unsupported version)")
    counts = {"members": 0, "candidates": 0, "experiments": 0, "skipped": 0}
    for m in data.get("members", []):
        if not db.get(orm.TeamMember, m["id"]) and not db.query(orm.TeamMember).filter_by(name=m["name"]).first():
            db.add(orm.TeamMember(id=m["id"], name=m["name"], role=m.get("role", "")))
            counts["members"] += 1
    db.flush()
    known_members = {m.id for m in db.scalars(select(orm.TeamMember))}
    for c in data.get("candidates", []):
        if db.get(orm.Candidate, c["id"]) or not db.get(orm.Challenge, c["challenge_id"]):
            counts["skipped"] += 1
            continue
        from ..generators.dedupe import fingerprint
        db.add(orm.Candidate(id=c["id"], challenge_id=c["challenge_id"], text=c["text"], fingerprint=fingerprint(c["text"]),
                             strategy_id=c.get("strategy_id"), method=c.get("method", "manual"), parent_ids=c.get("parent_ids", []),
                             generation=c.get("generation", 0), saved=c.get("saved", False), tags=c.get("tags", []), provenance=c.get("provenance", {})))
        counts["candidates"] += 1
    db.flush()
    known_cands = {c.id for c in db.scalars(select(orm.Candidate))}
    for e in data.get("experiments", []):
        if db.get(orm.Experiment, e["id"]) or not db.get(orm.Challenge, e["challenge_id"]):
            counts["skipped"] += 1
            continue
        from ..generators.dedupe import fingerprint
        db.add(orm.Experiment(id=e["id"], challenge_id=e["challenge_id"], candidate_id=e.get("candidate_id") if e.get("candidate_id") in known_cands else None,
                              owner_id=e.get("owner_id") if e.get("owner_id") in known_members else None, mode=e.get("mode", "api"),
                              prompt_text=e["prompt_text"], prompt_fingerprint=fingerprint(e["prompt_text"]), strategy_id=e.get("strategy_id"),
                              trial_index=e.get("trial_index", 0), tags=e.get("tags", []), notes=e.get("notes", ""),
                              created_at=e.get("created_at") or orm.now_iso()))
        db.flush()
        db.add(orm.Response(experiment_id=e["id"], text=e.get("response_text") or "", latency_ms=e.get("latency_ms"),
                            tokens_in=e.get("tokens_in"), tokens_out=e.get("tokens_out"), error=e.get("error"), meta={"imported": True}))
        db.add(orm.Evaluation(experiment_id=e["id"], verdict=e.get("verdict") or "failed", score=e.get("score") or 0.0,
                              details={"checks": e.get("checks", []), "imported": True}, reasons=e.get("reasons", []),
                              is_estimate=bool(e.get("is_estimate"))))
        counts["experiments"] += 1
    return counts


def backup_database() -> Path:
    s = get_settings()
    dest_dir = s.db_path.parent / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"promptforge-{datetime.now():%Y%m%d-%H%M%S}.db"
    src = sqlite3.connect(str(s.db_path))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)   # consistent online snapshot
    finally:
        dst.close()
        src.close()
    return dest
