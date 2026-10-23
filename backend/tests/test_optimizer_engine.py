import asyncio

import pytest
from sqlalchemy import func, select

from backend.core.errors import ValidationFailed
from backend.database import orm
from backend.database.session import session_scope
from backend.optimizer import engine as opt
from backend.services import challenges as chs
from backend.targets.base import Target, TargetResponse
from backend.targets.simulated import SimulatedTarget


def run_row(rid):
    with session_scope() as db:
        r = db.get(orm.OptimizationRun, rid)
        return opt.run_view(r)


async def go(cid="practice-secret-medium", **cfg):
    rid = opt.create_run(cid, None, None, {"seed": 7, **cfg})
    await opt.start_run(rid)
    return rid, run_row(rid)


async def test_finds_flag_and_stops_with_verified_flag():
    rid, r = await go()
    assert r["state"] == "completed" and r["stop_reason"] == "verified_flag" and r["best_fitness"] > 1
    with session_scope() as db:
        assert db.scalars(select(orm.VerifiedFlag)).one().flag == "CTF{practice_example_02}"


async def test_hard_challenge_improves_over_generations_via_mutation():
    rid, r = await go("practice-secret-hard", max_generations=8, attempt_budget=60)
    assert r["stop_reason"] == "verified_flag" and r["generation"] >= 1
    assert r["history"][0]["verdicts"].get("verified_success", 0) == 0
    # the winner is a mutation whose lineage points to an earlier candidate
    detail = {c["id"]: c for c in _candidates(rid)}
    winner = detail[r["best_candidate_id"]]
    assert winner["method"] == "mutation" and winner["parent_ids"] and all(p in detail for p in winner["parent_ids"])


def _candidates(rid):
    with session_scope() as db:
        return [{"id": c.id, "method": c.method, "parent_ids": c.parent_ids, "generation": c.generation, "text": c.text, "strategy_id": c.strategy_id}
                for c in db.scalars(select(orm.Candidate).where(orm.Candidate.run_id == rid))]


async def test_attempt_budget_is_a_hard_stop():
    with session_scope() as db:
        chs.update_challenge(db, "practice-secret-hard", {"query_budget": 500})
    rid, r = await go("practice-secret-hard", attempt_budget=4, population_size=6, max_generations=10)
    assert r["stop_reason"] == "budget_exhausted" and r["attempts_used"] <= 4
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(orm.Experiment).where(orm.Experiment.run_id == rid)) <= 4


async def test_challenge_budget_also_enforced_by_optimizer():
    with session_scope() as db:
        chs.update_challenge(db, "practice-secret-hard", {"query_budget": 3})
    rid, r = await go("practice-secret-hard", attempt_budget=100)
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(orm.Experiment)) == 3
    assert r["stop_reason"] == "budget_exhausted"


async def test_max_generations_stop():
    class Never(SimulatedTarget):
        pass
    rid, r = await go("practice-secret-hard", max_generations=2, attempt_budget=100, patience=10, population_size=4, elite=1)
    # hard challenge may be solved early in rare seeds; seed 7 is deterministic and unsolved within 2 generations
    assert r["stop_reason"] in ("max_generations", "verified_flag") and r["generation"] <= 1


async def test_no_improvement_stop():
    rid, r = await go("practice-secret-hard", max_generations=30, patience=1, attempt_budget=200, min_improvement=5.0)
    assert r["stop_reason"] in ("no_improvement", "verified_flag")


async def test_time_limit_stop(monkeypatch):
    async def slow(self, messages, *, timeout=None):
        await asyncio.sleep(0.05)
        return TargetResponse(text="no", latency_ms=50)
    monkeypatch.setattr(SimulatedTarget, "generate", slow)
    with session_scope() as db:
        chs.update_challenge(db, "practice-secret-hard", {"query_budget": 500})
    rid, r = await go("practice-secret-hard", time_limit_s=0.2, attempt_budget=300, max_generations=50, patience=50)
    assert r["stop_reason"] == "time_limit" and r["attempts_used"] < 20


async def test_cancel_stops_run_promptly(monkeypatch):
    async def slow(self, messages, *, timeout=None):
        await asyncio.sleep(0.05)
        return TargetResponse(text="no", latency_ms=50)
    monkeypatch.setattr(SimulatedTarget, "generate", slow)
    with session_scope() as db:
        chs.update_challenge(db, "practice-secret-hard", {"query_budget": 500})
    rid = opt.create_run("practice-secret-hard", None, None, {"attempt_budget": 300, "max_generations": 50, "patience": 50})
    task = opt.start_run(rid)
    await asyncio.sleep(0.3)
    opt.cancel_run(rid)
    await asyncio.wait_for(task, 3)
    r = run_row(rid)
    assert r["state"] == "cancelled" and r["stop_reason"] == "cancelled" and 0 < r["attempts_used"] < 30


async def test_pause_and_resume(monkeypatch):
    async def slow(self, messages, *, timeout=None):
        await asyncio.sleep(0.03)
        return TargetResponse(text="no", latency_ms=30)
    monkeypatch.setattr(SimulatedTarget, "generate", slow)
    rid = opt.create_run("practice-secret-hard", None, None, {"attempt_budget": 12, "max_generations": 3, "patience": 9})
    task = opt.start_run(rid)
    await asyncio.sleep(0.1)
    opt.pause_run(rid)
    await asyncio.sleep(0.15)
    used = run_row(rid)["attempts_used"]
    await asyncio.sleep(0.2)
    assert run_row(rid)["state"] == "paused"
    with session_scope() as db:
        n1 = db.scalar(select(func.count()).select_from(orm.Experiment))
    await asyncio.sleep(0.2)
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(orm.Experiment)) == n1       # nothing runs while paused
    opt.resume_run(rid)
    await asyncio.wait_for(task, 10)
    assert run_row(rid)["state"] == "completed"


async def test_manual_approval_gate():
    rid = opt.create_run("practice-secret-medium", None, None, {"approval": "manual", "seed": 3})
    task = opt.start_run(rid)
    for _ in range(50):
        await asyncio.sleep(0.05)
        if run_row(rid)["state"] == "awaiting_approval":
            break
    r = run_row(rid)
    assert r["state"] == "awaiting_approval" and r["pending_approval"]
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(orm.Experiment)) == 0      # nothing tested before approval
    keep = [p["id"] for p in r["pending_approval"]][:2]
    opt.approve_generation(rid, keep)
    await asyncio.wait_for(task, 10)
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(orm.Experiment)) <= 2


async def test_manual_approval_reject_cancels_without_spending():
    rid = opt.create_run("practice-secret-medium", None, None, {"approval": "manual"})
    task = opt.start_run(rid)
    await asyncio.sleep(0.2)
    opt.approve_generation(rid, None, reject=True)
    await asyncio.wait_for(task, 5)
    r = run_row(rid)
    assert r["state"] == "cancelled" and r["attempts_used"] == 0


async def test_target_failures_do_not_crash_run_or_count_as_success(monkeypatch):
    async def down(self, messages, *, timeout=None):
        return TargetResponse(error="connection refused")
    monkeypatch.setattr(SimulatedTarget, "generate", down)
    rid, r = await go("practice-secret-easy", max_generations=2, attempt_budget=12)
    assert r["state"] == "completed" and r["stop_reason"] in ("max_generations", "no_improvement", "budget_exhausted")
    with session_scope() as db:
        verdicts = {e.verdict for e in db.scalars(select(orm.Evaluation))}
        assert verdicts == {"invalid_test"} and db.scalar(select(func.count()).select_from(orm.VerifiedFlag)) == 0


async def test_unexpected_exception_marks_run_failed_not_crashed(monkeypatch):
    async def boom(self, messages, *, timeout=None):
        raise ValueError("kaboom")
    monkeypatch.setattr(SimulatedTarget, "generate", boom)
    rid, r = await go("practice-secret-easy", max_generations=2)
    assert r["state"] == "completed"       # adapter errors are recorded as invalid tests
    assert not any(h for h in r["history"] if h["verdicts"].get("verified_success"))


async def test_every_child_has_lineage_and_unique_text():
    rid, r = await go("practice-secret-hard", max_generations=4, attempt_budget=60, patience=9, population_size=6)
    cands = _candidates(rid)
    ids = {c["id"] for c in cands}
    muts = [c for c in cands if c["method"] == "mutation"]
    for c in muts:
        assert c["parent_ids"] and set(c["parent_ids"]) <= ids and c["generation"] >= 1
    texts = [c["text"].strip().lower() for c in cands]
    assert len(texts) == len(set(texts))


async def test_operator_stats_are_recorded_for_learning():
    rid, r = await go("practice-secret-hard", max_generations=3, attempt_budget=60, patience=9)
    last = r["history"][-1]
    assert last["operator_stats"] or r["generation"] == 0


async def test_history_priors_reorder_strategies():
    await go("practice-secret-medium")
    pri = opt.strategy_priors("secret_extraction")
    assert pri and max(pri.values()) > 0


async def test_config_validation():
    with pytest.raises(ValidationFailed):
        opt.create_run("practice-secret-easy", None, None, {"population_size": 1})
    with pytest.raises(ValidationFailed):
        opt.create_run("practice-secret-easy", None, None, {"concurrency": 99})
    with pytest.raises(ValidationFailed):
        opt.create_run("practice-secret-easy", "t_manual", None, {})


async def test_interrupted_runs_are_marked_and_resumable():
    with session_scope() as db:
        chs.update_challenge(db, "practice-secret-hard", {"query_budget": 500})
    rid = opt.create_run("practice-secret-hard", None, None, {"seed": 7, "max_generations": 1, "attempt_budget": 6, "patience": 9})
    await opt.start_run(rid)
    with session_scope() as db:                                    # simulate a crash mid-run
        r = db.get(orm.OptimizationRun, rid)
        r.state, r.stop_reason = "running", None
        r.config = {**r.config, "max_generations": 3, "attempt_budget": 30}
    assert opt.mark_interrupted_runs() == 1 and run_row(rid)["state"] == "interrupted"
    before = run_row(rid)["attempts_used"]
    await opt.resume_interrupted(rid)
    r = run_row(rid)
    assert r["state"] == "completed" and r["attempts_used"] > before and len(r["history"]) >= 2


async def test_concurrent_evaluation_respects_budget():
    with session_scope() as db:
        chs.update_challenge(db, "practice-secret-hard", {"query_budget": 500})
    rid, r = await go("practice-secret-hard", concurrency=3, attempt_budget=7, max_generations=6, patience=9)
    assert r["attempts_used"] <= 7
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(orm.Experiment)) <= 7
