"""Members, targets, challenges, strategies, system info."""
from __future__ import annotations

import shutil
from typing import Any

from fastapi import APIRouter, Body
from sqlalchemy import select

from ..core.config import get_settings
from ..core.errors import ValidationFailed
from ..database import orm
from ..database.session import session_scope
from ..services import challenges as chs
from ..services import members as mem
from ..services import targets as tgs
from ..strategies import library as lib
from ..targets.ollama import detect_ollama

router = APIRouter()


# ---- system --------------------------------------------------------------
@router.get("/health")
def health():
    s = get_settings()
    return {"status": "ok", "version": "1.0.0", "bind_host": s.host, "lan_enabled": s.allow_lan,
            "plugins_enabled": s.enable_plugins, "ollama_binary": shutil.which("ollama") is not None}


@router.get("/ollama")
async def ollama_status(base_url: str | None = None):
    return await detect_ollama(base_url)


# ---- members -------------------------------------------------------------
@router.get("/members")
def list_members():
    with session_scope() as db:
        return [mem.member_view(m) for m in db.scalars(select(orm.TeamMember).order_by(orm.TeamMember.name))]


@router.post("/members", status_code=201)
def add_member(body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        return mem.member_view(mem.create_member(db, body.get("name", ""), body.get("role", "")))


@router.delete("/members/{mid}", status_code=204)
def remove_member(mid: str):
    with session_scope() as db:
        mem.delete_member(db, mid)


# ---- targets -------------------------------------------------------------
@router.get("/targets")
def list_targets():
    with session_scope() as db:
        return [tgs.target_view(t) for t in db.scalars(select(orm.Target).order_by(orm.Target.name))]


@router.post("/targets", status_code=201)
def add_target(body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        return tgs.target_view(tgs.create_target(db, body))


@router.patch("/targets/{tid}")
def edit_target(tid: str, body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        return tgs.target_view(tgs.update_target(db, tid, body))


@router.delete("/targets/{tid}", status_code=204)
def remove_target(tid: str):
    with session_scope() as db:
        tgs.delete_target(db, tid)


@router.post("/targets/{tid}/check")
async def check_target(tid: str):
    with session_scope() as db:
        tgs.get_target(db, tid)
    with session_scope() as db:
        return await tgs.check_target(db, tid)


# ---- challenges ----------------------------------------------------------
@router.get("/challenges")
def list_challenges():
    with session_scope() as db:
        return [chs.public_view(db, c) for c in db.scalars(select(orm.Challenge).order_by(orm.Challenge.difficulty, orm.Challenge.name))]


@router.post("/challenges", status_code=201)
def add_challenge(body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        return chs.public_view(db, chs.create_challenge(db, body))


@router.get("/challenges/{cid}")
def read_challenge(cid: str):
    with session_scope() as db:
        return chs.public_view(db, chs.get_challenge(db, cid))


@router.patch("/challenges/{cid}")
def edit_challenge(cid: str, body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        return chs.public_view(db, chs.update_challenge(db, cid, body))


@router.delete("/challenges/{cid}", status_code=204)
def remove_challenge(cid: str):
    with session_scope() as db:
        c = chs.get_challenge(db, cid)
        if c.builtin:
            raise ValidationFailed("Built-in challenges cannot be deleted (set status to archived instead)")
        db.delete(c)


# ---- strategies ----------------------------------------------------------
@router.get("/strategies")
def list_strategies(challenge_type: str | None = None):
    with session_scope() as db:
        rows = db.scalars(select(orm.Strategy).order_by(orm.Strategy.category, orm.Strategy.name)).all()
        return [lib.strategy_to_dict(s) for s in rows if not challenge_type or not s.challenge_types or challenge_type in s.challenge_types]


@router.post("/strategies", status_code=201)
def add_strategy(body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        return lib.strategy_to_dict(lib.create_strategy(db, body))


@router.get("/strategies/export")
def export_strategies():
    with session_scope() as db:
        rows = db.scalars(select(orm.Strategy).where(orm.Strategy.builtin == False)).all()  # noqa: E712
        return [{f: getattr(s, f) for f in lib.FIELDS} | {"id": s.id} for s in rows]


@router.post("/strategies/import", status_code=201)
def import_strategies(body: list[dict[str, Any]] = Body(...)):
    with session_scope() as db:
        return [lib.strategy_to_dict(s) for s in lib.import_strategies(db, body)]


@router.patch("/strategies/{sid}")
def edit_strategy(sid: str, body: dict[str, Any] = Body(...)):
    with session_scope() as db:
        return lib.strategy_to_dict(lib.update_strategy(db, sid, body))


@router.post("/strategies/{sid}/duplicate", status_code=201)
def dup_strategy(sid: str):
    with session_scope() as db:
        return lib.strategy_to_dict(lib.duplicate_strategy(db, sid))


@router.delete("/strategies/{sid}", status_code=204)
def remove_strategy(sid: str):
    with session_scope() as db:
        lib.delete_strategy(db, sid)


@router.post("/strategies/{sid}/render")
def render_strategy(sid: str, body: dict[str, Any] = Body(default={})):
    """Render a strategy with explicit variables (preview)."""
    with session_scope() as db:
        s = db.get(orm.Strategy, sid)
        if s is None:
            raise ValidationFailed("Strategy not found")
        return {"prompts": [lib.render_strategy(s, body.get("variables", {}), i) for i in range(len(lib.templates_of(s)))]}
