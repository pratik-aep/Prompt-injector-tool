"""Challenge management. Secrets (evaluator_config, defender) never leave this layer via public_view."""
from __future__ import annotations

import json
import re
from typing import Any

import jsonschema
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.errors import NotFound, ValidationFailed
from ..core.security import secrets_registry
from ..database import orm

TYPES = ("secret_extraction", "instruction_hierarchy", "format_enforcement", "indirect_injection", "tool_output_trust")
DIFFICULTIES = ("easy", "medium", "hard")
STATUSES = ("active", "solved", "archived")
CHECK_KINDS = ("exact_flag", "regex", "json_schema", "constraint", "plugin")
EDITABLE = ("name", "description", "difficulty", "type", "target_id", "objective", "allowed_surface", "scoring",
            "query_budget", "max_prompt_length", "allowed_methods", "status", "evaluator_config", "defender")


def register_secrets(c: orm.Challenge) -> None:
    for chk in (c.evaluator_config or {}).get("checks", []):
        if chk.get("kind") == "exact_flag":
            secrets_registry.register(chk.get("flag"))


def validate_evaluator_config(cfg: dict[str, Any]) -> None:
    if not isinstance(cfg, dict):
        raise ValidationFailed("evaluator_config must be an object")
    if cfg.get("combine", "all") not in ("all", "any"):
        raise ValidationFailed("combine must be 'all' or 'any'")
    for chk in cfg.get("checks", []):
        k = chk.get("kind")
        if k not in CHECK_KINDS:
            raise ValidationFailed(f"Unknown check kind '{k}'. Valid: {', '.join(CHECK_KINDS)}")
        if k == "exact_flag" and not chk.get("flag"):
            raise ValidationFailed("exact_flag check needs 'flag'")
        if k == "regex":
            try:
                re.compile(chk.get("pattern", ""))
            except re.error as e:
                raise ValidationFailed(f"Invalid regex: {e}") from e
        if k == "json_schema":
            try:
                jsonschema.Draft202012Validator.check_schema(chk.get("schema", {}))
            except jsonschema.SchemaError as e:
                raise ValidationFailed(f"Invalid JSON schema: {e.message}") from e


def _validate(data: dict[str, Any]) -> None:
    if "type" in data and data["type"] not in TYPES:
        raise ValidationFailed(f"type must be one of: {', '.join(TYPES)}")
    if "difficulty" in data and data["difficulty"] not in DIFFICULTIES:
        raise ValidationFailed(f"difficulty must be one of: {', '.join(DIFFICULTIES)}")
    if "status" in data and data["status"] not in STATUSES:
        raise ValidationFailed(f"status must be one of: {', '.join(STATUSES)}")
    if "query_budget" in data and not (1 <= int(data["query_budget"]) <= 10_000):
        raise ValidationFailed("query_budget must be between 1 and 10000")
    if "max_prompt_length" in data and not (10 <= int(data["max_prompt_length"]) <= 50_000):
        raise ValidationFailed("max_prompt_length must be between 10 and 50000")
    for m in data.get("allowed_methods", []):
        if m not in ("api", "manual"):
            raise ValidationFailed("allowed_methods may contain 'api' and/or 'manual'")
    if "evaluator_config" in data:
        validate_evaluator_config(data["evaluator_config"])


def get_challenge(db: Session, cid: str) -> orm.Challenge:
    c = db.get(orm.Challenge, cid)
    if c is None:
        raise NotFound("Challenge not found")
    return c


def attempts_used(db: Session, cid: str) -> int:
    return db.scalar(select(func.count()).select_from(orm.Experiment).where(orm.Experiment.challenge_id == cid)) or 0


def public_view(db: Session, c: orm.Challenge) -> dict[str, Any]:
    used = attempts_used(db, c.id)
    flags = db.scalars(select(orm.VerifiedFlag).where(orm.VerifiedFlag.challenge_id == c.id)).all()
    return {
        "id": c.id, "name": c.name, "description": c.description, "difficulty": c.difficulty, "type": c.type,
        "target_id": c.target_id, "objective": c.objective, "allowed_surface": c.allowed_surface,
        "scoring": c.scoring, "query_budget": c.query_budget, "max_prompt_length": c.max_prompt_length,
        "allowed_methods": c.allowed_methods, "status": c.status, "builtin": c.builtin,
        "attempts_used": used, "attempts_remaining": max(0, c.query_budget - used),
        "has_defender_prompt": bool((c.defender or {}).get("system_prompt")),
        "has_local_evaluator": bool((c.evaluator_config or {}).get("checks")),
        "verified_flags": [{"flag": f.flag, "experiment_id": f.experiment_id, "member_id": f.member_id,
                            "source": f.source, "created_at": f.created_at} for f in flags],
        "created_at": c.created_at, "updated_at": c.updated_at,
    }


def create_challenge(db: Session, data: dict[str, Any], *, builtin: bool = False) -> orm.Challenge:
    if not data.get("name") or not data.get("type"):
        raise ValidationFailed("name and type are required")
    _validate(data)
    row = orm.Challenge(builtin=builtin)
    if data.get("id"):
        if db.get(orm.Challenge, data["id"]):
            raise ValidationFailed(f"Challenge id '{data['id']}' already exists")
        row.id = data["id"]
    for k in EDITABLE:
        if k in data:
            setattr(row, k, data[k])
    if data.get("target_id") and db.get(orm.Target, data["target_id"]) is None:
        raise ValidationFailed("target_id does not exist")
    db.add(row)
    db.flush()
    register_secrets(row)
    return row


def update_challenge(db: Session, cid: str, data: dict[str, Any]) -> orm.Challenge:
    row = get_challenge(db, cid)
    _validate(data)
    for k in EDITABLE:
        if k in data:
            setattr(row, k, data[k])
    db.flush()
    register_secrets(row)
    return row


def seed_challenges(db: Session) -> int:
    n = 0
    d = get_settings().challenges_dir
    for f in sorted(d.glob("*.json")):
        item = json.loads(f.read_text())
        row = db.get(orm.Challenge, item["id"])
        if row is None:
            create_challenge(db, item, builtin=True)
        else:  # refresh definition but keep status
            keep = row.status
            for k in EDITABLE:
                if k in item:
                    setattr(row, k, item[k])
            row.status, row.builtin = keep, True
            register_secrets(row)
        n += 1
    return n


def register_all_secrets(db: Session) -> None:
    for c in db.scalars(select(orm.Challenge)):
        register_secrets(c)
