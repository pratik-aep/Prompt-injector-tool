"""Generation, candidates, experiments, sessions."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query
from sqlalchemy import select

from ..core.errors import NotFound, ValidationFailed
from ..database import orm
from ..database.session import session_scope
from ..experiments import runner
from ..experiments.candidates import candidate_view, save_draft
from ..generators.base import GenerationRequest
from ..generators.service import generate_candidates
from ..services import challenges as chs
from ..services import experiments as exs
from ..services.targets import get_target

router = APIRouter()


# ---- generation / candidates --------------------------------------------
@router.post("/generate")
async def generate(body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        c = chs.get_challenge(db, body["challenge_id"])
        pub = chs.public_view(db, c)          # generators only ever see the public view
        strategies = list(db.scalars(select(orm.Strategy)))
        existing = [t for (t,) in db.execute(select(orm.Candidate.text).where(orm.Candidate.challenge_id == c.id))]
        previous = [{"text": e.prompt_text, "verdict": v.verdict, "score": v.score}
                    for e, v in db.execute(select(orm.Experiment, orm.Evaluation).join(orm.Evaluation, orm.Evaluation.experiment_id == orm.Experiment.id)
                                           .where(orm.Experiment.challenge_id == c.id).order_by(orm.Experiment.created_at.desc()).limit(10))]
        llm = None
        if body.get("llm_target_id"):
            llm = runner.instantiate_target(get_target(db, body["llm_target_id"]), {})
    req = GenerationRequest(pub, mode=body.get("mode", "template"), strategy_ids=body.get("strategy_ids"), count=int(body.get("count", 6)),
                            previous=previous, constraints=body.get("constraints", ""), manual_text=body.get("manual_text", ""),
                            budget_remaining=pub["attempts_remaining"])
    drafts, warnings = await generate_candidates(req, strategies, llm=llm, existing_texts=[] if req.mode == "manual" else existing)
    with session_scope() as db:
        rows = [save_draft(db, c.id, d, owner_id=body.get("owner_id")) for d in drafts]
        return {"candidates": [candidate_view(r) for r in rows], "warnings": warnings}


@router.get("/candidates")
def list_candidates(challenge_id: str | None = None, saved: bool | None = None, run_id: str | None = None, limit: int = 100, offset: int = 0):
    with session_scope() as db:
        stmt = select(orm.Candidate).order_by(orm.Candidate.created_at.desc())
        if challenge_id:
            stmt = stmt.where(orm.Candidate.challenge_id == challenge_id)
        if saved is not None:
            stmt = stmt.where(orm.Candidate.saved == saved)
        if run_id:
            stmt = stmt.where(orm.Candidate.run_id == run_id)
        return [candidate_view(c) for c in db.scalars(stmt.limit(min(limit, 500)).offset(offset))]


@router.patch("/candidates/{cid}")
def edit_candidate(cid: str, body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        c = db.get(orm.Candidate, cid)
        if c is None:
            raise NotFound("Candidate not found")
        if "saved" in body:
            c.saved = bool(body["saved"])
        if "tags" in body:
            c.tags = sorted(set(map(str, body["tags"])))
        return candidate_view(c)


# ---- experiments ---------------------------------------------------------
@router.post("/experiments/run")
async def run_experiment(body: dict[str, Any] = Body(...)):
    common = dict(target_id=body.get("target_id"), owner_id=body.get("owner_id"), strategy_id=body.get("strategy_id"),
                  candidate_id=body.get("candidate_id"), tags=body.get("tags"), judge_target_id=body.get("judge_target_id"))
    if body.get("session_id"):
        return await runner.execute_turn(body["challenge_id"], body["prompt"], session_id=body["session_id"], **common)
    return await runner.run_candidate(body["challenge_id"], body["prompt"], trials=int(body.get("trials", 1)), **common)


@router.post("/experiments/manual", status_code=201)
async def manual_experiment(body: dict[str, Any] = Body(...)):
    return await runner.submit_manual(body["challenge_id"], body["prompt"], body.get("response", ""), owner_id=body.get("owner_id"),
                                      strategy_id=body.get("strategy_id"), candidate_id=body.get("candidate_id"),
                                      tags=body.get("tags"), notes=body.get("notes", ""))


@router.post("/experiments/{eid}/confirm-flag")
def confirm_flag(eid: str, body: dict[str, Any] = Body(...)):
    return runner.confirm_flag(eid, body.get("flag", ""), body.get("member_id"))


@router.get("/experiments")
def list_experiments(challenge_id: str | None = None, owner_id: str | None = None, verdict: str | None = None,
                     strategy_id: str | None = None, mode: str | None = None, run_id: str | None = None, q: str | None = None,
                     tag: str | None = None, target_id: str | None = None, limit: int = Query(50, le=200), offset: int = 0):
    with session_scope() as db:
        return exs.list_experiments(db, challenge_id=challenge_id, owner_id=owner_id, verdict=verdict, strategy_id=strategy_id, mode=mode,
                                    run_id=run_id, q=q, tag=tag, target_id=target_id, limit=limit, offset=offset)


@router.get("/experiments/{eid}")
def read_experiment(eid: str):
    with session_scope() as db:
        return exs.get_experiment(db, eid)


@router.patch("/experiments/{eid}")
def edit_experiment(eid: str, body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        return exs.annotate(db, eid, notes=body.get("notes"), tags=body.get("tags"), owner_id=body.get("owner_id"))


@router.post("/experiments/compare")
def compare_experiments(body: dict[str, Any] = Body(...)):
    ids = body.get("ids", [])
    if not 2 <= len(ids) <= 5:
        raise ValidationFailed("Provide between 2 and 5 experiment ids")
    with session_scope() as db:
        return exs.compare(db, ids)


@router.get("/challenges/{cid}/duplicates")
def duplicates(cid: str):
    with session_scope() as db:
        return exs.find_duplicates(db, cid)


# ---- sessions (multi-turn) ----------------------------------------------
@router.post("/sessions", status_code=201)
def new_session(body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        c = chs.get_challenge(db, body["challenge_id"])
        s = runner.create_session(db, c.id, body.get("target_id") or c.target_id or "t_simulated", body.get("owner_id"), int(body.get("turn_limit", 10)))
        return runner.session_view(s)


@router.get("/sessions/{sid}")
def read_session(sid: str):
    with session_scope() as db:
        s = db.get(orm.ConversationSession, sid)
        if s is None:
            raise NotFound("Session not found")
        return runner.session_view(s)


@router.get("/sessions")
def list_sessions(challenge_id: str):
    with session_scope() as db:
        return [runner.session_view(s) for s in db.scalars(select(orm.ConversationSession).where(orm.ConversationSession.challenge_id == challenge_id)
                                                           .order_by(orm.ConversationSession.created_at.desc()).limit(50))]


@router.post("/sessions/{sid}/messages")
async def session_message(sid: str, body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        s = db.get(orm.ConversationSession, sid)
        if s is None:
            raise NotFound("Session not found")
        cid, tid, oid = s.challenge_id, s.target_id, s.owner_id
    return await runner.execute_turn(cid, body["text"], target_id=tid, owner_id=body.get("owner_id") or oid, session_id=sid,
                                     strategy_id=body.get("strategy_id"), tags=body.get("tags"))


@router.post("/sessions/{sid}/branch", status_code=201)
def branch_session(sid: str, body: dict[str, Any] = Body(default={})):
    with session_scope() as db:
        parent = db.get(orm.ConversationSession, sid)
        if parent is None:
            raise NotFound("Session not found")
        s = runner.create_session(db, parent.challenge_id, parent.target_id, parent.owner_id, parent.turn_limit, parent, body.get("turn"))
        return runner.session_view(s)


@router.post("/sessions/{sid}/reset", status_code=201)
def reset_session(sid: str):
    with session_scope() as db:
        old = db.get(orm.ConversationSession, sid)
        if old is None:
            raise NotFound("Session not found")
        return runner.session_view(runner.create_session(db, old.challenge_id, old.target_id, old.owner_id, old.turn_limit))
