"""Target registry service: explicit registration, scope validation, health checks."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..core.errors import NotFound, PromptForgeError, ValidationFailed
from ..core.security import resolve_secret
from ..database import orm
from ..targets.registry import REMOTE_KINDS, build_target, validate_target_config


def target_view(t: orm.Target) -> dict[str, Any]:
    cred = None
    if t.secret_ref:
        try:
            cred = bool(resolve_secret(t.secret_ref))
        except PromptForgeError:
            cred = False
    return {"id": t.id, "name": t.name, "kind": t.kind, "config": t.config, "secret_ref": t.secret_ref,
            "credential_available": cred, "enabled": t.enabled, "allow_private": t.allow_private,
            "remote": t.kind in REMOTE_KINDS, "created_at": t.created_at, "updated_at": t.updated_at}


def get_target(db: Session, tid: str) -> orm.Target:
    t = db.get(orm.Target, tid)
    if t is None:
        raise NotFound("Target not found")
    return t


def create_target(db: Session, data: dict[str, Any]) -> orm.Target:
    if not data.get("name") or not data.get("kind"):
        raise ValidationFailed("name and kind are required")
    if data.get("secret_ref"):
        resolve_secret(data["secret_ref"])  # validates the format only
        if "env:" in data["secret_ref"] and len(data["secret_ref"]) > 80:
            raise ValidationFailed("secret_ref looks like a raw secret; supply 'env:NAME' or 'keychain:SERVICE', never the key itself")
    allow_private = bool(data.get("allow_private", False))
    cfg = validate_target_config(data["kind"], data.get("config") or {}, allow_private)
    if db.query(orm.Target).filter_by(name=data["name"]).first():
        raise ValidationFailed(f"A target named '{data['name']}' already exists")
    t = orm.Target(name=data["name"], kind=data["kind"], config=cfg, secret_ref=data.get("secret_ref"),
                   enabled=bool(data.get("enabled", True)), allow_private=allow_private)
    db.add(t)
    db.flush()
    return t


def update_target(db: Session, tid: str, data: dict[str, Any]) -> orm.Target:
    t = get_target(db, tid)
    allow_private = bool(data.get("allow_private", t.allow_private))
    if "config" in data:
        t.config = validate_target_config(t.kind, data["config"], allow_private)
    for k in ("name", "secret_ref", "enabled"):
        if k in data:
            setattr(t, k, data[k])
    t.allow_private = allow_private
    db.flush()
    return t


def delete_target(db: Session, tid: str) -> None:
    db.delete(get_target(db, tid))


async def check_target(db: Session, tid: str) -> dict[str, Any]:
    t = get_target(db, tid)
    try:
        return await build_target(t).health()
    except PromptForgeError as e:
        return {"ok": False, "detail": str(e)}


def seed_default_targets(db: Session) -> None:
    for name, kind, cfg in (("Local simulator", "simulated", {}), ("Manual (paste responses)", "manual", {})):
        if not db.query(orm.Target).filter_by(name=name).first():
            db.add(orm.Target(id="t_simulated" if kind == "simulated" else "t_manual", name=name, kind=kind, config=cfg))
    db.flush()
