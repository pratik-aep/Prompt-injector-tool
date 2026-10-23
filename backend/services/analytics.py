"""Aggregations computed from real stored data only."""
from __future__ import annotations

import statistics
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..database import orm

V = "verified_success"


def _rate(hits: int, valid: int) -> float:
    return round(hits / valid, 4) if valid else 0.0


def overview(db: Session) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(orm.Experiment)) or 0
    verified = db.scalar(select(func.count()).select_from(orm.Evaluation).where(orm.Evaluation.verdict == V)) or 0
    invalid = db.scalar(select(func.count()).select_from(orm.Evaluation).where(orm.Evaluation.verdict.in_(["invalid_test", "evaluation_error"]))) or 0
    possible = db.scalar(select(func.count()).select_from(orm.Evaluation).where(orm.Evaluation.verdict == "possible_success")) or 0
    active = db.scalars(select(orm.Challenge).where(orm.Challenge.status != "archived")).all()
    used = dict(db.execute(select(orm.Experiment.challenge_id, func.count()).group_by(orm.Experiment.challenge_id)).all())
    remaining = sum(max(0, c.query_budget - used.get(c.id, 0)) for c in active)
    recent = db.execute(select(orm.Experiment, orm.Evaluation).outerjoin(orm.Evaluation, orm.Evaluation.experiment_id == orm.Experiment.id)
                        .order_by(orm.Experiment.created_at.desc()).limit(8)).all()
    return {
        "active_challenges": len([c for c in active if c.status == "active"]), "solved_challenges": len([c for c in active if c.status == "solved"]),
        "total_attempts": total, "verified_successes": verified, "possible_successes": possible, "invalid_tests": invalid,
        "success_rate": _rate(verified, total - invalid), "remaining_budget": remaining,
        "recent_experiments": [{"id": e.id, "challenge_id": e.challenge_id, "created_at": e.created_at, "mode": e.mode,
                                "prompt_preview": e.prompt_text[:120], "verdict": v.verdict if v else None} for e, v in recent],
    }


def by_strategy(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(select(orm.Experiment.strategy_id, func.count(),
                             func.sum(case((orm.Evaluation.verdict == V, 1), else_=0)),
                             func.sum(case((orm.Evaluation.verdict == "possible_success", 1), else_=0)),
                             func.sum(case((orm.Evaluation.verdict.in_(["invalid_test", "evaluation_error"]), 1), else_=0)))
                      .join(orm.Evaluation, orm.Evaluation.experiment_id == orm.Experiment.id)
                      .group_by(orm.Experiment.strategy_id)).all()
    names = {s.id: s.name for s in db.scalars(select(orm.Strategy))}
    out = [{"strategy_id": sid or "(custom / manual)", "name": names.get(sid, "Custom / manual prompt"), "attempts": n, "verified": v or 0,
            "possible": p or 0, "invalid": i or 0, "success_rate": _rate(v or 0, n - (i or 0))} for sid, n, v, p, i in rows]
    return sorted(out, key=lambda r: (-r["success_rate"], -r["attempts"]))


def by_challenge(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(select(orm.Challenge.id, orm.Challenge.name, orm.Challenge.query_budget, func.count(orm.Experiment.id),
                             func.sum(case((orm.Evaluation.verdict == V, 1), else_=0)))
                      .outerjoin(orm.Experiment, orm.Experiment.challenge_id == orm.Challenge.id)
                      .outerjoin(orm.Evaluation, orm.Evaluation.experiment_id == orm.Experiment.id)
                      .group_by(orm.Challenge.id)).all()
    return [{"challenge_id": cid, "name": n, "budget": b, "attempts": a, "verified": v or 0} for cid, n, b, a, v in rows]


def by_target(db: Session) -> list[dict[str, Any]]:
    """Model comparison + latency + token usage per target."""
    rows = db.execute(select(orm.Target.id, orm.Target.name, orm.Target.kind, orm.Experiment.id, orm.Evaluation.verdict,
                             orm.Response.latency_ms, orm.Response.tokens_in, orm.Response.tokens_out)
                      .join(orm.Experiment, orm.Experiment.target_id == orm.Target.id)
                      .outerjoin(orm.Evaluation, orm.Evaluation.experiment_id == orm.Experiment.id)
                      .outerjoin(orm.Response, orm.Response.experiment_id == orm.Experiment.id)).all()
    agg: dict[str, dict[str, Any]] = {}
    for tid, name, kind, _eid, verdict, lat, tin, tout in rows:
        a = agg.setdefault(tid, {"target_id": tid, "name": name, "kind": kind, "attempts": 0, "verified": 0, "invalid": 0,
                                 "lat": [], "tokens_in": 0, "tokens_out": 0})
        a["attempts"] += 1
        a["verified"] += verdict == V
        a["invalid"] += verdict in ("invalid_test", "evaluation_error")
        if lat and verdict != "invalid_test":
            a["lat"].append(lat)
        a["tokens_in"] += tin or 0
        a["tokens_out"] += tout or 0
    out = []
    for a in agg.values():
        lat = sorted(a.pop("lat"))
        a["avg_latency_ms"] = round(statistics.fmean(lat), 1) if lat else None
        a["p95_latency_ms"] = round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1) if lat else None
        a["success_rate"] = _rate(a["verified"], a["attempts"] - a["invalid"])
        out.append(a)
    return out


def optimization_runs(db: Session) -> list[dict[str, Any]]:
    out = []
    for r in db.scalars(select(orm.OptimizationRun).order_by(orm.OptimizationRun.created_at.desc()).limit(20)):
        out.append({"run_id": r.id, "challenge_id": r.challenge_id, "state": r.state, "stop_reason": r.stop_reason,
                    "attempts_used": r.attempts_used,
                    "series": [{"generation": h["generation"], "best_fitness": h["best_fitness"], "mean_fitness": h["mean_fitness"]} for h in (r.history or [])]})
    return out


def full_analytics(db: Session) -> dict[str, Any]:
    return {"by_strategy": by_strategy(db), "by_challenge": by_challenge(db), "by_target": by_target(db), "runs": optimization_runs(db)}
