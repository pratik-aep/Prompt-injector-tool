"""SQLAlchemy ORM models (schema is created by SQL migrations, not create_all)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


class Base(DeclarativeBase):
    pass


class _Stamped:
    created_at: Mapped[str] = mapped_column(String, default=now_iso)


class _Updated(_Stamped):
    updated_at: Mapped[str] = mapped_column(String, default=now_iso, onupdate=now_iso)


class TeamMember(Base, _Updated):
    __tablename__ = "team_members"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("m_"))
    name: Mapped[str] = mapped_column(String, unique=True)
    role: Mapped[str] = mapped_column(String, default="")


class Target(Base, _Updated):
    __tablename__ = "targets"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("t_"))
    name: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    secret_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_private: Mapped[bool] = mapped_column(Boolean, default=False)


class Challenge(Base, _Updated):
    __tablename__ = "challenges"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("c_"))
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[str] = mapped_column(String, default="easy")
    type: Mapped[str] = mapped_column(String)
    target_id: Mapped[str | None] = mapped_column(ForeignKey("targets.id", ondelete="SET NULL"), nullable=True)
    objective: Mapped[str] = mapped_column(Text, default="")
    allowed_surface: Mapped[str] = mapped_column(Text, default="")
    scoring: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    query_budget: Mapped[int] = mapped_column(Integer, default=50)
    max_prompt_length: Mapped[int] = mapped_column(Integer, default=2000)
    allowed_methods: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["api", "manual"])
    status: Mapped[str] = mapped_column(String, default="active")
    evaluator_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    defender: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)


class Strategy(Base, _Updated):
    __tablename__ = "strategies"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("s_"))
    category: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    challenge_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    template: Mapped[str] = mapped_column(Text)
    required_inputs: Mapped[list[str]] = mapped_column(JSON, default=list)
    variants: Mapped[list[str]] = mapped_column(JSON, default=list)
    trust_boundary: Mapped[str] = mapped_column(Text, default="")
    limitations: Mapped[str] = mapped_column(Text, default="")
    evaluation_criteria: Mapped[str] = mapped_column(Text, default="")
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)


class OptimizationRun(Base, _Updated):
    __tablename__ = "optimization_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("r_"))
    challenge_id: Mapped[str] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"))
    target_id: Mapped[str | None] = mapped_column(ForeignKey("targets.id", ondelete="SET NULL"), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String, default="pending")
    generation: Mapped[int] = mapped_column(Integer, default=0)
    attempts_used: Mapped[int] = mapped_column(Integer, default=0)
    best_candidate_id: Mapped[str | None] = mapped_column(String, nullable=True)
    best_fitness: Mapped[float] = mapped_column(Float, default=0.0)
    stop_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    history: Mapped[list[Any]] = mapped_column(JSON, default=list)
    pending_approval: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)


class Candidate(Base, _Stamped):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("p_"))
    challenge_id: Mapped[str] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String)
    strategy_id: Mapped[str | None] = mapped_column(String, nullable=True)
    method: Mapped[str] = mapped_column(String)
    parent_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("optimization_runs.id", ondelete="SET NULL"), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True)
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ConversationSession(Base, _Updated):
    __tablename__ = "conversation_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("cs_"))
    challenge_id: Mapped[str] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"))
    target_id: Mapped[str | None] = mapped_column(ForeignKey("targets.id", ondelete="SET NULL"), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True)
    parent_session_id: Mapped[str | None] = mapped_column(ForeignKey("conversation_sessions.id", ondelete="SET NULL"), nullable=True)
    branch_turn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    messages: Mapped[list[Any]] = mapped_column(JSON, default=list)
    turn_limit: Mapped[int] = mapped_column(Integer, default=10)


class Experiment(Base, _Stamped):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("e_"))
    challenge_id: Mapped[str] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"))
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True)
    target_id: Mapped[str | None] = mapped_column(ForeignKey("targets.id", ondelete="SET NULL"), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("optimization_runs.id", ondelete="SET NULL"), nullable=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("conversation_sessions.id", ondelete="SET NULL"), nullable=True)
    mode: Mapped[str] = mapped_column(String, default="api")
    prompt_text: Mapped[str] = mapped_column(Text)
    prompt_fingerprint: Mapped[str] = mapped_column(String)
    strategy_id: Mapped[str | None] = mapped_column(String, nullable=True)
    trial_index: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")


class Response(Base, _Stamped):
    __tablename__ = "responses"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("rs_"))
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), unique=True)
    text: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Evaluation(Base, _Stamped):
    __tablename__ = "evaluations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("ev_"))
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), unique=True)
    verdict: Mapped[str] = mapped_column(String)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=False)


class VerifiedFlag(Base, _Stamped):
    __tablename__ = "verified_flags"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("f_"))
    challenge_id: Mapped[str] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"))
    experiment_id: Mapped[str | None] = mapped_column(ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True)
    member_id: Mapped[str | None] = mapped_column(ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True)
    flag: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, default="evaluator")


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String, default=now_iso, onupdate=now_iso)
