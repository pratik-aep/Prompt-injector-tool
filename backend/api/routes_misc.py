"""Optimisation runs, analytics, export/import, settings."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from ..core.errors import NotFound
from ..database import orm
from ..database.session import session_scope
from ..optimizer import engine as opt
from ..services import analytics, exports

router = APIRouter()


# ---- optimisation runs ---------------------------------------------------
@router.post("/runs", status_code=201)
async def create_and_start(body: dict[str, Any] = Body(...)):
    rid = opt.create_run(body["challenge_id"], body.get("target_id"), body.get("owner_id"), body.get("config", {}))
    opt.start_run(rid)
    with session_scope() as db:
        return opt.run_view(db.get(orm.OptimizationRun, rid))


@router.get("/runs")
def list_runs(challenge_id: str | None = None):
    with session_scope() as db:
        stmt = select(orm.OptimizationRun).order_by(orm.OptimizationRun.created_at.desc()).limit(50)
        if challenge_id:
            stmt = stmt.where(orm.OptimizationRun.challenge_id == challenge_id)
        return [opt.run_view(r) for r in db.scalars(stmt)]


@router.get("/runs/{rid}")
def read_run(rid: str):
    with session_scope() as db:
        r = db.get(orm.OptimizationRun, rid)
        if r is None:
            raise NotFound("Run not found")
        out = opt.run_view(r)
        cands = db.scalars(select(orm.Candidate).where(orm.Candidate.run_id == rid).order_by(orm.Candidate.generation, orm.Candidate.created_at)).all()
        out["candidates"] = [{"id": c.id, "text": c.text, "strategy_id": c.strategy_id, "method": c.method, "parent_ids": c.parent_ids,
                              "generation": c.generation, "fitness": (c.provenance or {}).get("fitness"), "verdict": (c.provenance or {}).get("verdict"),
                              "op": (c.provenance or {}).get("op"), "experiment_id": (c.provenance or {}).get("experiment_id"),
                              "components": (c.provenance or {}).get("components")} for c in cands]
        out["active"] = rid in opt._controllers
        return out


@router.post("/runs/{rid}/pause")
async def pause(rid: str):
    opt.pause_run(rid)
    return {"ok": True}


@router.post("/runs/{rid}/resume")
async def resume(rid: str):
    opt.resume_run(rid)
    return {"ok": True}


@router.post("/runs/{rid}/cancel")
async def cancel(rid: str):
    opt.cancel_run(rid)
    return {"ok": True}


@router.post("/runs/{rid}/approve")
async def approve(rid: str, body: dict[str, Any] = Body(default={})):
    opt.approve_generation(rid, body.get("approved_ids"))
    return {"ok": True}


@router.post("/runs/{rid}/reject")
async def reject(rid: str):
    opt.approve_generation(rid, None, reject=True)
    return {"ok": True}


@router.post("/runs/{rid}/continue")
async def continue_interrupted(rid: str):
    opt.resume_interrupted(rid)
    return {"ok": True}


# ---- analytics -----------------------------------------------------------
@router.get("/analytics/overview")
def overview():
    with session_scope() as db:
        return analytics.overview(db)


@router.get("/analytics")
def full():
    with session_scope() as db:
        return analytics.full_analytics(db)


# ---- export / import / backup -------------------------------------------
@router.get("/export/json")
def export_json(challenge_id: str | None = None):
    with session_scope() as db:
        return exports.export_json(db, challenge_id)


@router.get("/export/csv", response_class=PlainTextResponse)
def export_csv(challenge_id: str | None = None):
    with session_scope() as db:
        return PlainTextResponse(exports.export_csv(db, challenge_id), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=promptforge-experiments.csv"})


@router.post("/import/json")
def import_json(body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        return exports.import_json(db, body)


@router.post("/backup")
def backup():
    return {"path": str(exports.backup_database())}


# ---- settings ------------------------------------------------------------
@router.get("/settings")
def get_settings_kv():
    with session_scope() as db:
        return {s.key: s.value for s in db.scalars(select(orm.AppSetting))}


@router.put("/settings/{key}")
def put_setting(key: str, body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        row = db.get(orm.AppSetting, key)
        if row is None:
            row = orm.AppSetting(key=key, value="")
            db.add(row)
        row.value = str(body.get("value", ""))
        return {key: row.value}
