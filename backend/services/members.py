from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.errors import NotFound, ValidationFailed
from ..database import orm


def create_member(db: Session, name: str, role: str = "") -> orm.TeamMember:
    name = (name or "").strip()
    if not name:
        raise ValidationFailed("name is required")
    if db.query(orm.TeamMember).filter_by(name=name).first():
        raise ValidationFailed(f"Member '{name}' already exists")
    m = orm.TeamMember(name=name, role=role)
    db.add(m)
    db.flush()
    return m


def delete_member(db: Session, mid: str) -> None:
    m = db.get(orm.TeamMember, mid)
    if m is None:
        raise NotFound("Member not found")
    db.delete(m)


def member_view(m: orm.TeamMember) -> dict:
    return {"id": m.id, "name": m.name, "role": m.role, "created_at": m.created_at}
