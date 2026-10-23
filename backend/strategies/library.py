"""Strategy files -> DB, plus prompt rendering. Strategy content lives in templates/strategies/*.json."""
from __future__ import annotations

import base64
import codecs
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.errors import NotFound, PromptForgeError, ValidationFailed
from ..database import orm

TURN_SEPARATOR = "---TURN---"
_VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_FILLER = ("The committee reviewed the schedule for the coming weeks and noted that several departments had updated their "
           "reporting calendars. Facilities confirmed that routine maintenance would continue as planned, and the library "
           "extended its opening hours. ")
FIELDS = ("category", "name", "description", "challenge_types", "template", "required_inputs", "variants",
          "trust_boundary", "limitations", "evaluation_criteria")


def derived_variables(vars_: dict[str, Any]) -> dict[str, str]:
    out = {k: str(v) for k, v in vars_.items()}
    goal = out.get("goal", "")
    out.setdefault("b64_goal", base64.b64encode(goal.encode()).decode())
    out.setdefault("rot13_goal", codecs.encode(goal, "rot13"))
    out.setdefault("reversed_goal", goal[::-1])
    out.setdefault("filler", (_FILLER * int(out.get("filler_repeats", "6"))).strip())
    return out


def render_template(template: str, variables: dict[str, Any]) -> str:
    v = derived_variables(variables)
    missing = sorted({m for m in _VAR.findall(template) if m not in v})
    if missing:
        raise ValidationFailed(f"Missing template variable(s): {', '.join(missing)}")
    return _VAR.sub(lambda m: v[m.group(1)], template)


def templates_of(s: orm.Strategy) -> list[str]:
    return [s.template, *(s.variants or [])]


def render_strategy(s: orm.Strategy, variables: dict[str, Any], variant: int = 0) -> str:
    ts = templates_of(s)
    return render_template(ts[variant % len(ts)], variables)


def load_builtin_files() -> list[dict[str, Any]]:
    d = get_settings().strategies_dir
    items: list[dict[str, Any]] = []
    for f in sorted(d.glob("*.json")):
        data = json.loads(f.read_text())
        items.extend(data if isinstance(data, list) else [data])
    return items


def seed_builtin_strategies(db: Session) -> int:
    n = 0
    for item in load_builtin_files():
        row = db.get(orm.Strategy, item["id"])
        if row is None:
            row = orm.Strategy(id=item["id"], builtin=True, template="")
            db.add(row)
        for f in FIELDS:
            if f in item:
                setattr(row, f, item[f])
        row.builtin = True
        n += 1
    db.flush()
    return n


def strategy_to_dict(s: orm.Strategy) -> dict[str, Any]:
    d = {f: getattr(s, f) for f in FIELDS}
    d.update(id=s.id, builtin=s.builtin, created_at=s.created_at, updated_at=s.updated_at)
    return d


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    out = {f: data[f] for f in FIELDS if f in data}
    if not out.get("template") or not out.get("name"):
        raise ValidationFailed("Strategy needs at least a name and a template")
    out.setdefault("category", "Custom")
    used = {m for t in [out["template"], *(out.get("variants") or [])] for m in _VAR.findall(t)}
    derived = {"b64_goal", "rot13_goal", "reversed_goal", "filler", "filler_repeats"}
    required = set(out.get("required_inputs") or []) | (used - derived)
    if used & {"b64_goal", "rot13_goal", "reversed_goal"}:
        required.add("goal")
    out["required_inputs"] = sorted(required)
    return out


def create_strategy(db: Session, data: dict[str, Any]) -> orm.Strategy:
    clean = _clean(data)
    row = orm.Strategy(**clean, builtin=False)
    if data.get("id"):
        if db.get(orm.Strategy, data["id"]):
            raise ValidationFailed(f"Strategy id '{data['id']}' already exists")
        row.id = data["id"]
    db.add(row)
    db.flush()
    return row


def update_strategy(db: Session, sid: str, data: dict[str, Any]) -> orm.Strategy:
    row = db.get(orm.Strategy, sid)
    if row is None:
        raise NotFound("Strategy not found")
    if row.builtin:
        raise PromptForgeError("Built-in strategies are read-only; duplicate one to customise it", 409)
    merged = {**strategy_to_dict(row), **data}
    for k, v in _clean(merged).items():
        setattr(row, k, v)
    db.flush()
    return row


def duplicate_strategy(db: Session, sid: str) -> orm.Strategy:
    src = db.get(orm.Strategy, sid)
    if src is None:
        raise NotFound("Strategy not found")
    d = strategy_to_dict(src)
    d["name"] = f"{src.name} (copy)"
    return create_strategy(db, {k: d[k] for k in FIELDS} | {"name": d["name"]})


def delete_strategy(db: Session, sid: str) -> None:
    row = db.get(orm.Strategy, sid)
    if row is None:
        raise NotFound("Strategy not found")
    if row.builtin:
        raise PromptForgeError("Built-in strategies cannot be deleted", 409)
    db.delete(row)


def import_strategies(db: Session, items: list[dict[str, Any]]) -> list[orm.Strategy]:
    """Import user strategies. Imported items are never marked built-in; ids are regenerated on collision."""
    out = []
    for it in items:
        data = {k: v for k, v in it.items() if k in FIELDS}
        if it.get("id") and db.get(orm.Strategy, it["id"]) is None:
            data["id"] = it["id"]
        out.append(create_strategy(db, data))
    return out
