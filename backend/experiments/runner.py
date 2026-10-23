"""Execute one attempt end to end: budget -> target call -> evaluation -> persistence."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import BudgetExceeded, NotFound, PromptForgeError, ScopeViolation, ValidationFailed
from ..database import orm
from ..database.session import session_scope
from ..evaluators.base import CheckResult, EvaluationResult, Verdict
from ..evaluators.engine import evaluate_response, external_flag_evaluation
from ..evaluators.judge import ai_judge
from ..generators.dedupe import fingerprint
from ..services.challenges import attempts_used, get_challenge
from ..services.targets import get_target
from ..strategies.library import TURN_SEPARATOR
from ..targets.base import Message, Target, TargetResponse
from ..targets.registry import build_target
from ..targets.simulated import SimulatedTarget

log = logging.getLogger(__name__)
_locks: dict[str, asyncio.Lock] = {}
RANK = {Verdict.VERIFIED_SUCCESS.value: 4, Verdict.POSSIBLE_SUCCESS.value: 3, Verdict.FAILED.value: 2,
        Verdict.INVALID_TEST.value: 1, Verdict.EVALUATION_ERROR.value: 0}


def _lock(cid: str) -> asyncio.Lock:
    return _locks.setdefault(cid, asyncio.Lock())


def split_turns(text: str) -> list[str]:
    parts = [p.strip() for p in text.split(TURN_SEPARATOR)]
    return [p for p in parts if p]


def render_user_turn(defender: dict[str, Any], text: str) -> str:
    """Wrap attacker text in the challenge's trusted template (e.g. a document or tool-output frame)."""
    tmpl = (defender or {}).get("user_template") or "{{attack}}"
    return tmpl.replace("{{attack}}", text)


def build_messages(defender: dict[str, Any], history: list[dict[str, str]], new_user_text: str) -> list[Message]:
    """System text only ever comes from trusted challenge config; all attacker text is role=user."""
    msgs: list[Message] = []
    if (defender or {}).get("system_prompt"):
        msgs.append(Message("system", defender["system_prompt"]))
    for h in history:
        msgs.append(Message(h["role"], render_user_turn(defender, h["content"]) if h["role"] == "user" else h["content"]))
    msgs.append(Message("user", render_user_turn(defender, new_user_text)))
    return msgs


def instantiate_target(row: orm.Target, defender: dict[str, Any], transport=None) -> Target:
    if row.kind == "simulated":
        if not row.enabled:
            raise ScopeViolation(f"Target '{row.name}' is disabled")
        return SimulatedTarget({"behavior": (defender or {}).get("simulator", {})})
    return build_target(row, transport=transport)


# ---- sessions --------------------------------------------------------------

def create_session(db: Session, challenge_id: str, target_id: str | None, owner_id: str | None,
                   turn_limit: int = 10, parent: orm.ConversationSession | None = None, branch_turn: int | None = None) -> orm.ConversationSession:
    msgs: list[dict[str, str]] = []
    if parent is not None:
        # branch: copy history up to (and including) `branch_turn` user/assistant pairs
        keep = (branch_turn if branch_turn is not None else len(parent.messages) // 2) * 2
        msgs = [dict(m) for m in parent.messages[:keep]]
    s = orm.ConversationSession(challenge_id=challenge_id, target_id=target_id, owner_id=owner_id, turn_limit=turn_limit,
                                parent_session_id=parent.id if parent else None, branch_turn=branch_turn, messages=msgs)
    db.add(s)
    db.flush()
    return s


def session_view(s: orm.ConversationSession) -> dict[str, Any]:
    return {"id": s.id, "challenge_id": s.challenge_id, "target_id": s.target_id, "owner_id": s.owner_id,
            "parent_session_id": s.parent_session_id, "branch_turn": s.branch_turn, "messages": s.messages,
            "turn_limit": s.turn_limit, "turns": len(s.messages) // 2, "created_at": s.created_at}


# ---- persistence helpers ---------------------------------------------------

def _persist_outcome(db: Session, exp: orm.Experiment, resp: TargetResponse, ev: EvaluationResult,
                     challenge: orm.Challenge, member_id: str | None, source: str = "evaluator") -> None:
    db.add(orm.Response(experiment_id=exp.id, text=resp.text, latency_ms=resp.latency_ms, tokens_in=resp.tokens_in,
                        tokens_out=resp.tokens_out, error=resp.error, meta=resp.meta))
    db.add(orm.Evaluation(experiment_id=exp.id, verdict=ev.verdict.value, score=ev.score, details=ev.to_details(),
                          reasons=ev.reasons, is_estimate=ev.is_estimate))
    if ev.verdict == Verdict.VERIFIED_SUCCESS:
        flag = ev.verified_flag
        if flag and not db.scalar(select(orm.VerifiedFlag).where(orm.VerifiedFlag.challenge_id == challenge.id,
                                                                 orm.VerifiedFlag.flag == flag)):
            db.add(orm.VerifiedFlag(challenge_id=challenge.id, experiment_id=exp.id, member_id=member_id, flag=flag, source=source))
        if challenge.status == "active":
            challenge.status = "solved"


def _result_dict(exp: orm.Experiment, resp: TargetResponse, ev: EvaluationResult, duplicate_of: str | None, session_id: str | None) -> dict[str, Any]:
    return {"experiment_id": exp.id, "verdict": ev.verdict.value, "score": ev.score, "reasons": ev.reasons,
            "is_estimate": ev.is_estimate, "response_text": resp.text, "error": resp.error, "latency_ms": resp.latency_ms,
            "tokens_in": resp.tokens_in, "tokens_out": resp.tokens_out, "duplicate_of": duplicate_of,
            "session_id": session_id, "verified": ev.verdict == Verdict.VERIFIED_SUCCESS, "prompt_text": exp.prompt_text,
            "candidate_id": exp.candidate_id, "checks": ev.to_details()["checks"]}


def _reserve(db: Session, c: orm.Challenge, **fields: Any) -> tuple[orm.Experiment, str | None]:
    if attempts_used(db, c.id) >= c.query_budget:
        raise BudgetExceeded(f"Query budget exhausted for '{c.name}' ({c.query_budget} attempts)")
    fp = fingerprint(fields["prompt_text"])
    dup = db.scalar(select(orm.Experiment.id).where(orm.Experiment.challenge_id == c.id,
                                                    orm.Experiment.prompt_fingerprint == fp).limit(1))
    exp = orm.Experiment(challenge_id=c.id, prompt_fingerprint=fp, **fields)
    db.add(exp)
    db.flush()
    return exp, dup


# ---- API attempts ----------------------------------------------------------

async def execute_turn(challenge_id: str, text: str, *, target_id: str | None = None, owner_id: str | None = None,
                       session_id: str | None = None, strategy_id: str | None = None, candidate_id: str | None = None,
                       run_id: str | None = None, trial_index: int = 0, tags: list[str] | None = None,
                       judge_target_id: str | None = None, transport=None) -> dict[str, Any]:
    """Send one user turn to the target and record it. Counts as one query."""
    async with _lock(challenge_id):
        with session_scope() as db:
            c = get_challenge(db, challenge_id)
            if "api" not in (c.allowed_methods or []):
                raise ScopeViolation("API testing is not allowed for this challenge")
            if not text.strip():
                raise ValidationFailed("Prompt is empty")
            if len(text) > c.max_prompt_length:
                raise ValidationFailed(f"Prompt is {len(text)} characters; the limit is {c.max_prompt_length}")
            tid = target_id or c.target_id or "t_simulated"
            trow = get_target(db, tid)
            if trow.kind == "manual":
                raise ValidationFailed("Target is manual; use manual submission instead")
            sess = db.get(orm.ConversationSession, session_id) if session_id else create_session(db, c.id, tid, owner_id)
            if sess is None or sess.challenge_id != c.id:
                raise NotFound("Session not found for this challenge")
            if len(sess.messages) // 2 >= sess.turn_limit:
                raise ValidationFailed(f"Session turn limit ({sess.turn_limit}) reached; reset or branch the session")
            target = instantiate_target(trow, c.defender, transport)   # scope check happens here
            exp, dup = _reserve(db, c, candidate_id=candidate_id, target_id=tid, owner_id=owner_id, run_id=run_id,
                                session_id=sess.id, mode="api", prompt_text=text, strategy_id=strategy_id,
                                trial_index=trial_index, tags=tags or [])
            history = [dict(m) for m in sess.messages]
            defender, ev_cfg, objective = dict(c.defender or {}), dict(c.evaluator_config or {}), c.objective
            exp_id, sess_id = exp.id, sess.id
    msgs = build_messages(defender, history, text)
    try:
        resp = await target.generate(msgs)
    except asyncio.CancelledError:
        with session_scope() as db:
            exp = db.get(orm.Experiment, exp_id)
            ch = get_challenge(db, challenge_id)
            ev = EvaluationResult(Verdict.INVALID_TEST, 0.0, ["Cancelled before completion"])
            _persist_outcome(db, exp, TargetResponse(error="cancelled"), ev, ch, owner_id)
        raise
    except PromptForgeError as e:
        resp = TargetResponse(error=str(e))
    except Exception as e:  # noqa: BLE001 - a misbehaving adapter must not crash the run
        log.warning("target adapter failure: %s", type(e).__name__)
        resp = TargetResponse(error=f"Target adapter failed ({type(e).__name__})")
    ev = evaluate_response(resp.text, ev_cfg, prompt=text, target_error=resp.error) if ev_cfg.get("checks") \
        else external_flag_evaluation(resp.text, text, resp.error)
    if judge_target_id and ev.verdict == Verdict.FAILED and resp.ok:
        ev = await _apply_judge(ev, ev_cfg, ev.verdict, judge_target_id, objective, resp.text, text)
    with session_scope() as db:
        exp = db.get(orm.Experiment, exp_id)
        ch = get_challenge(db, challenge_id)
        _persist_outcome(db, exp, resp, ev, ch, owner_id)
        if resp.ok:
            s = db.get(orm.ConversationSession, sess_id)
            s.messages = [*s.messages, {"role": "user", "content": text}, {"role": "assistant", "content": resp.text}]
        out = _result_dict(exp, resp, ev, dup, sess_id)
    return out


async def _apply_judge(ev: EvaluationResult, ev_cfg: dict[str, Any], _v: Verdict, judge_target_id: str, objective: str,
                       response: str, prompt: str) -> EvaluationResult:
    try:
        with session_scope() as db:
            jt = instantiate_target(get_target(db, judge_target_id), {})
        chk: CheckResult = await ai_judge(jt, objective, response)
    except PromptForgeError as e:
        chk = CheckResult("ai_judge", False, 0.0, f"Judge unavailable: {e}", deterministic=False)
    return evaluate_response(response, ev_cfg, prompt=prompt, extra_checks=[chk])


async def run_candidate(challenge_id: str, text: str, *, trials: int = 1, **kw: Any) -> dict[str, Any]:
    """Run a (possibly multi-turn) prompt ``trials`` times in fresh sessions; aggregate for reliability."""
    turns = split_turns(text) or [text]
    trial_results: list[dict[str, Any]] = []
    for t in range(max(1, trials)):
        sess_id = None
        best: dict[str, Any] | None = None
        per_turn: list[dict[str, Any]] = []
        for turn in turns:
            r = await execute_turn(challenge_id, turn if len(turns) > 1 else text, session_id=sess_id, trial_index=t, **kw)
            sess_id = r["session_id"]
            per_turn.append({k: r[k] for k in ("experiment_id", "verdict", "score")})
            if best is None or (RANK[r["verdict"]], r["score"]) > (RANK[best["verdict"]], best["score"]):
                best = r
            if r["verdict"] == Verdict.VERIFIED_SUCCESS.value or r["verdict"] == Verdict.INVALID_TEST.value:
                break
        assert best is not None
        best = {**best, "turns": per_turn}
        trial_results.append(best)
    n = len(trial_results)
    verified = sum(r["verdict"] == Verdict.VERIFIED_SUCCESS.value for r in trial_results)
    top = max(trial_results, key=lambda r: (RANK[r["verdict"]], r["score"]))
    return {**top, "trials": n, "success_rate": verified / n, "trial_results": trial_results,
            "queries_used": sum(len(r["turns"]) for r in trial_results)}


# ---- manual mode -----------------------------------------------------------

async def submit_manual(challenge_id: str, prompt: str, response_text: str, *, owner_id: str | None = None,
                        strategy_id: str | None = None, candidate_id: str | None = None, tags: list[str] | None = None,
                        notes: str = "") -> dict[str, Any]:
    """Human relayed the prompt to an external chatbot and pasted the reply back."""
    async with _lock(challenge_id):
        with session_scope() as db:
            c = get_challenge(db, challenge_id)
            if "manual" not in (c.allowed_methods or []):
                raise ScopeViolation("Manual testing is not allowed for this challenge")
            if not prompt.strip():
                raise ValidationFailed("Prompt is empty")
            if len(prompt) > c.max_prompt_length:
                raise ValidationFailed(f"Prompt is {len(prompt)} characters; the limit is {c.max_prompt_length}")
            exp, dup = _reserve(db, c, candidate_id=candidate_id, target_id="t_manual" if db.get(orm.Target, "t_manual") else None,
                                owner_id=owner_id, mode="manual", prompt_text=prompt, strategy_id=strategy_id, tags=tags or [], notes=notes)
            cfg = dict(c.evaluator_config or {})
            resp = TargetResponse(text=response_text[:20_000], meta={"source": "manual"})
            ev = evaluate_response(resp.text, cfg, prompt=prompt) if cfg.get("checks") else external_flag_evaluation(resp.text, prompt)
            _persist_outcome(db, exp, resp, ev, c, owner_id)
            return _result_dict(exp, resp, ev, dup, None)


def confirm_flag(experiment_id: str, flag: str, member_id: str | None = None) -> dict[str, Any]:
    """Human attests that the competition's own verifier accepted ``flag``. Only path to verified for external challenges."""
    with session_scope() as db:
        exp = db.get(orm.Experiment, experiment_id)
        if exp is None:
            raise NotFound("Experiment not found")
        resp = db.scalar(select(orm.Response).where(orm.Response.experiment_id == exp.id))
        if resp is None or flag not in (resp.text or ""):
            raise ValidationFailed("That flag does not appear in this experiment's response")
        ev = db.scalar(select(orm.Evaluation).where(orm.Evaluation.experiment_id == exp.id))
        ev.verdict, ev.score, ev.is_estimate = Verdict.VERIFIED_SUCCESS.value, 1.0, False
        ev.reasons = [*ev.reasons, "Confirmed by competition verifier (user attestation)"]
        c = get_challenge(db, exp.challenge_id)
        if not db.scalar(select(orm.VerifiedFlag).where(orm.VerifiedFlag.challenge_id == c.id, orm.VerifiedFlag.flag == flag)):
            db.add(orm.VerifiedFlag(challenge_id=c.id, experiment_id=exp.id, member_id=member_id, flag=flag, source="competition_verifier"))
        if c.status == "active":
            c.status = "solved"
        return {"experiment_id": exp.id, "verdict": ev.verdict}
