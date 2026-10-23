"""Adaptive, feedback-driven prompt optimisation loop (evolutionary search + bandit operator selection)."""
from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from sqlalchemy import func, select

from ..core.errors import BudgetExceeded, NotFound, PromptForgeError, ValidationFailed
from ..database import orm
from ..database.session import session_scope
from ..experiments.candidates import save_draft
from ..experiments.runner import instantiate_target, run_candidate, split_turns
from ..generators.ai import generate_with_llm
from ..generators.base import Draft, GenerationRequest
from ..generators.dedupe import diverse_subset, fingerprint, is_near_duplicate, novelty
from ..generators.service import generate_candidates
from ..generators.template import generate_from_templates, public_variables
from ..services.challenges import get_challenge, public_view
from .fitness import FitnessWeights, compute_fitness
from .mutations import OPERATORS, MutationContext, apply_operator

log = logging.getLogger(__name__)

TERMINAL = {"completed", "cancelled", "failed"}


@dataclass
class OptimizerConfig:
    population_size: int = 6
    max_generations: int = 5
    attempt_budget: int = 30
    time_limit_s: float | None = None
    patience: int = 5
    min_improvement: float = 0.01
    trials: int = 1
    concurrency: int = 1
    approval: str = "auto"             # auto | manual (approve every generation before testing)
    elite: int = 2
    seed: int | None = None
    strategy_ids: list[str] | None = None
    seed_prompts: list[str] = field(default_factory=list)
    llm_target_id: str | None = None   # enables hybrid generation + LLM rewording
    judge_target_id: str | None = None
    similarity_threshold: float = 0.85
    weights: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OptimizerConfig":
        known = {f.name for f in fields(cls)}
        cfg = cls(**{k: v for k, v in d.items() if k in known})
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not 2 <= self.population_size <= 30:
            raise ValidationFailed("population_size must be between 2 and 30")
        if not 1 <= self.max_generations <= 50:
            raise ValidationFailed("max_generations must be between 1 and 50")
        if self.attempt_budget < 1:
            raise ValidationFailed("attempt_budget must be at least 1")
        if not 1 <= self.trials <= 10:
            raise ValidationFailed("trials must be between 1 and 10")
        if not 1 <= self.concurrency <= 4:
            raise ValidationFailed("concurrency must be between 1 and 4")
        if self.approval not in ("auto", "manual"):
            raise ValidationFailed("approval must be 'auto' or 'manual'")
        if self.elite < 0 or self.elite >= self.population_size:
            raise ValidationFailed("elite must be >= 0 and < population_size")


@dataclass
class Individual:
    cand_id: str
    text: str
    strategy_id: str | None
    parent_ids: list[str]
    generation: int
    method: str
    op: str | None = None
    parent_fitness: float | None = None
    fitness: float | None = None
    components: dict[str, float] = field(default_factory=dict)
    verdict: str | None = None
    score: float = 0.0
    experiment_id: str | None = None
    queries: int = 0


class Controller:
    """In-process control handle for one run (pause/resume/cancel/approval)."""

    def __init__(self) -> None:
        self.cancel = asyncio.Event()
        self.running = asyncio.Event()
        self.running.set()
        self.decision = asyncio.Event()
        self.approved_ids: list[str] | None = None
        self.rejected = False
        self.task: asyncio.Task | None = None


_controllers: dict[str, Controller] = {}


def controller(run_id: str) -> Controller:
    return _controllers.setdefault(run_id, Controller())


def run_view(r: orm.OptimizationRun) -> dict[str, Any]:
    return {"id": r.id, "challenge_id": r.challenge_id, "target_id": r.target_id, "owner_id": r.owner_id, "config": r.config,
            "state": r.state, "generation": r.generation, "attempts_used": r.attempts_used,
            "best_candidate_id": r.best_candidate_id, "best_fitness": r.best_fitness, "stop_reason": r.stop_reason,
            "history": r.history, "pending_approval": r.pending_approval, "created_at": r.created_at, "updated_at": r.updated_at}


def _set_run(run_id: str, **fields_: Any) -> None:
    with session_scope() as db:
        r = db.get(orm.OptimizationRun, run_id)
        for k, v in fields_.items():
            setattr(r, k, v)


def strategy_priors(challenge_type: str) -> dict[str, float]:
    """Historical verified-success rate per strategy for this challenge type (feedback across runs)."""
    with session_scope() as db:
        rows = db.execute(
            select(orm.Experiment.strategy_id, func.count(), func.sum((orm.Evaluation.verdict == "verified_success").cast(orm.Integer)))
            .join(orm.Evaluation, orm.Evaluation.experiment_id == orm.Experiment.id)
            .join(orm.Challenge, orm.Challenge.id == orm.Experiment.challenge_id)
            .where(orm.Challenge.type == challenge_type, orm.Experiment.strategy_id.is_not(None))
            .group_by(orm.Experiment.strategy_id)).all()
    return {sid: (hits or 0) / n for sid, n, hits in rows}


class OptimizationEngine:
    def __init__(self, run_id: str, transport=None):
        self.run_id = run_id
        self.transport = transport
        self.ctl = controller(run_id)
        with session_scope() as db:
            r = db.get(orm.OptimizationRun, run_id)
            if r is None:
                raise NotFound("Run not found")
            c = get_challenge(db, r.challenge_id)
            self.cfg = OptimizerConfig.from_dict(r.config)
            self.challenge = public_view(db, c)       # PUBLIC view only: no evaluator/defender secrets
            self.target_id = r.target_id
            self.owner_id = r.owner_id
            self.challenge_id = c.id
            self.strategies = list(db.scalars(select(orm.Strategy)))
            self.tested_texts = [t for (t,) in db.execute(select(orm.Experiment.prompt_text).where(orm.Experiment.challenge_id == c.id))]
            self.generation = r.generation
            self.attempts_used = r.attempts_used
            self.history: list[dict[str, Any]] = list(r.history or [])
            self.best_fitness = r.best_fitness
            self.best_id = r.best_candidate_id
        self.rng = random.Random(self.cfg.seed)
        self.weights = FitnessWeights.from_dict(self.cfg.weights)
        self.archive: list[Individual] = []        # every evaluated individual
        self.op_stats: dict[str, list[float]] = {}     # op -> [n, total_gain]
        self.strat_stats: dict[str, list[float]] = {}  # strategy -> [n, total_fitness]
        self.t0 = time.monotonic()
        self.stop_reason: str | None = None
        self.llm = None
        self._stale = 0

    # -- helpers --------------------------------------------------------
    def _time_up(self) -> bool:
        return self.cfg.time_limit_s is not None and time.monotonic() - self.t0 >= self.cfg.time_limit_s

    def _cost(self, text: str) -> int:
        return self.cfg.trials * max(1, len(split_turns(text)))

    def _remaining(self) -> int:
        return self.cfg.attempt_budget - self.attempts_used

    def _load_llm(self):
        if self.cfg.llm_target_id and self.llm is None:
            with session_scope() as db:
                row = db.get(orm.Target, self.cfg.llm_target_id)
                if row is None:
                    raise ValidationFailed("llm_target_id does not exist")
                self.llm = instantiate_target(row, {}, self.transport)

    def _persist(self, state: str | None = None, **kw: Any) -> None:
        upd: dict[str, Any] = dict(generation=self.generation, attempts_used=self.attempts_used, history=self.history,
                                   best_fitness=self.best_fitness, best_candidate_id=self.best_id)
        if state:
            upd["state"] = state
        upd.update(kw)
        _set_run(self.run_id, **upd)

    # -- generation 0 ---------------------------------------------------
    async def _initial_population(self) -> list[Draft]:
        n = self.cfg.population_size
        drafts: list[Draft] = [Draft(t, "manual", provenance={"seed": True}) for t in self.cfg.seed_prompts if t.strip()]
        priors = strategy_priors(self.challenge["type"])
        ordered = sorted(self.strategies, key=lambda s: (-priors.get(s.id, 0.0), s.id))
        req = GenerationRequest(self.challenge, mode="hybrid" if self.llm else "template", strategy_ids=self.cfg.strategy_ids,
                                count=n * 2, similarity_threshold=self.cfg.similarity_threshold)
        gen, _warn = await generate_candidates(req, ordered, llm=self.llm, existing_texts=self.tested_texts + [d.text for d in drafts])
        drafts.extend(gen)
        keep = diverse_subset([d.text for d in drafts], n) if len(drafts) > n else range(len(drafts))
        # honour seed prompts first, then diverse generated ones
        chosen = [drafts[i] for i in keep]
        return chosen

    # -- next generation --------------------------------------------------
    def _ucb_op(self) -> str:
        unseen = [o for o in OPERATORS if o not in self.op_stats]
        if unseen:
            return self.rng.choice(unseen)
        total = sum(s[0] for s in self.op_stats.values())
        def score(o: str) -> float:
            n, gain = self.op_stats[o]
            return gain / n + 0.3 * math.sqrt(math.log(total + 1) / n)
        return max(OPERATORS, key=score)

    def _pick_parent(self, penalise: dict[str | None, int], exclude: Individual | None = None) -> Individual:
        pool = [i for i in self.archive if i is not exclude and i.fitness is not None] or self.archive
        k = min(3, len(pool))
        contenders = self.rng.sample(pool, k)
        # diversity pressure: prefer strategies that are under-represented among this generation's children
        return max(contenders, key=lambda i: (i.fitness or 0.0) + 0.05 - 0.04 * penalise.get(i.strategy_id, 0) + self.rng.random() * 0.01)

    def _make_children(self, n: int) -> list[Draft]:
        children: list[Draft] = []
        seen = self.tested_texts + [i.text for i in self.archive]
        penal: dict[str | None, int] = {}
        goal = public_variables(self.challenge).get("goal", "")
        tries = 0
        while len(children) < n and tries < n * 12 and self.archive:
            tries += 1
            parent = self._pick_parent(penal)
            op = self._ucb_op()
            other = None
            if op == "crossover":
                others = [i for i in self.archive if i.strategy_id != parent.strategy_id and i is not parent]
                if not others:
                    op = self.rng.choice([o for o in OPERATORS if o != "crossover"])
                else:
                    other = self._pick_parent(penal, exclude=parent) if len(others) > 1 else others[0]
            text = apply_operator(op, parent.text, MutationContext(self.rng, goal, other.text if other else None))
            if not text or len(text) > self.challenge["max_prompt_length"]:
                continue
            if is_near_duplicate(text, seen + [c.text for c in children], self.cfg.similarity_threshold + 0.07):
                continue
            parents = [parent] + ([other] if other else [])
            children.append(Draft(text, "mutation", parent.strategy_id, [p.cand_id for p in parents], self.generation,
                                  {"op": op, "parent_fitness": parent.fitness}))
            penal[parent.strategy_id] = penal.get(parent.strategy_id, 0) + 1
        if len(children) < n:   # exploration: untried template variants
            fresh = generate_from_templates(self.strategies, self.challenge, ids=self.cfg.strategy_ids,
                                            max_len=self.challenge["max_prompt_length"])
            for d in fresh:
                if len(children) >= n:
                    break
                if not is_near_duplicate(d.text, seen + [c.text for c in children], self.cfg.similarity_threshold):
                    d.generation = self.generation
                    d.provenance["op"] = "fresh_template"
                    children.append(d)
        return children

    async def _llm_reword(self, drafts: list[Draft]) -> None:
        """Hybrid mode: replace up to a third of mutations with LLM rewordings of the same parent."""
        if self.llm is None:
            return
        by_id = {i.cand_id: i for i in self.archive}
        for d in drafts[: max(1, len(drafts) // 3)]:
            if d.method != "mutation" or not d.parent_ids:
                continue
            parent = by_id.get(d.parent_ids[0])
            req = GenerationRequest(self.challenge, mode="ai", count=1)
            new, _err = await generate_with_llm(self.llm, req, [], seeds=[parent.text if parent else d.text], method="mutation")
            if new and not is_near_duplicate(new[0].text, self.tested_texts + [i.text for i in self.archive]):
                d.text, d.provenance["op"] = new[0].text, "llm_reword"

    # -- evaluation -------------------------------------------------------
    async def _wait_if_paused(self) -> bool:
        """Return False if the run should stop."""
        await self.ctl.running.wait()
        return not self.ctl.cancel.is_set()

    async def _approval_gate(self, inds: list[Individual]) -> list[Individual] | None:
        if self.cfg.approval != "manual":
            return inds
        self.ctl.decision.clear()
        self.ctl.approved_ids, self.ctl.rejected = None, False
        pending = [{"id": i.cand_id, "text": i.text, "strategy_id": i.strategy_id, "parent_ids": i.parent_ids, "op": i.op} for i in inds]
        self._persist("awaiting_approval", pending_approval=pending)
        waiters = [asyncio.create_task(self.ctl.decision.wait()), asyncio.create_task(self.ctl.cancel.wait())]
        await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        for w in waiters:
            w.cancel()
        if self.ctl.cancel.is_set() or self.ctl.rejected:
            return None
        ok = set(self.ctl.approved_ids) if self.ctl.approved_ids is not None else {i.cand_id for i in inds}
        self._persist("running", pending_approval=None)
        return [i for i in inds if i.cand_id in ok]

    async def _evaluate(self, inds: list[Individual]) -> None:
        sem = asyncio.Semaphore(self.cfg.concurrency)

        async def one(ind: Individual) -> None:
            async with sem:
                if not await self._wait_if_paused() or self._time_up() or self.stop_reason in ("budget_exhausted", "failed"):
                    return
                cost = self._cost(ind.text)
                if cost > self._remaining():
                    return
                self.attempts_used += cost                       # reserve before the call (concurrency-safe)
                try:
                    res = await run_candidate(self.challenge_id, ind.text, trials=self.cfg.trials, target_id=self.target_id,
                                              owner_id=self.owner_id, strategy_id=ind.strategy_id, candidate_id=ind.cand_id,
                                              run_id=self.run_id, judge_target_id=self.cfg.judge_target_id, transport=self.transport)
                except BudgetExceeded:
                    self.attempts_used -= cost
                    self.stop_reason = "budget_exhausted"
                    return
                self.attempts_used += res["queries_used"] - cost    # true-up (early exit on multi-turn)
                nov = novelty(ind.text, [a.text for a in self.archive if a is not ind] + self.tested_texts)
                comp = compute_fitness(res, nov, res["queries_used"], self.cfg.attempt_budget, self.weights)
                ind.fitness, ind.components = comp["fitness"], comp
                ind.verdict, ind.score, ind.experiment_id, ind.queries = res["verdict"], res["score"], res["experiment_id"], res["queries_used"]

        await asyncio.gather(*(one(i) for i in inds))

    def _record_generation(self, inds: list[Individual]) -> bool:
        """Update archive/stats/history; return True if the best fitness improved meaningfully."""
        evaluated = [i for i in inds if i.fitness is not None]
        improvements = []
        for i in evaluated:
            self.archive.append(i)
            self.tested_texts.append(i.text)
            sid = i.strategy_id or "_none"
            st = self.strat_stats.setdefault(sid, [0, 0.0])
            st[0] += 1
            st[1] += i.fitness or 0.0
            if i.op and i.parent_fitness is not None:
                gain = (i.fitness or 0.0) - i.parent_fitness
                o = self.op_stats.setdefault(i.op, [0, 0.0])
                o[0] += 1
                o[1] += gain
                improvements.append({"child": i.cand_id, "parent": i.parent_ids[0] if i.parent_ids else None, "op": i.op, "delta": round(gain, 4)})
        with session_scope() as db:
            for i in evaluated:
                c = db.get(orm.Candidate, i.cand_id)
                if c:
                    c.provenance = {**(c.provenance or {}), "fitness": i.fitness, "components": i.components, "verdict": i.verdict,
                                    "experiment_id": i.experiment_id, "op": i.op, "parent_fitness": i.parent_fitness}
        prev_best = self.best_fitness
        if evaluated:
            top = max(evaluated, key=lambda i: i.fitness or -1)
            if (top.fitness or 0) > self.best_fitness or self.best_id is None:
                self.best_fitness, self.best_id = top.fitness or 0.0, top.cand_id
        counts: dict[str, int] = {}
        for i in evaluated:
            counts[i.verdict or "unknown"] = counts.get(i.verdict or "unknown", 0) + 1
        self.history.append({
            "generation": self.generation, "evaluated": len(evaluated), "attempts_used": self.attempts_used,
            "best_fitness": self.best_fitness, "generation_best": max((i.fitness or 0 for i in evaluated), default=0),
            "mean_fitness": round(sum(i.fitness or 0 for i in evaluated) / len(evaluated), 4) if evaluated else 0,
            "verdicts": counts, "improvements": sorted(improvements, key=lambda x: -x["delta"])[:5],
            "operator_stats": {k: {"n": v[0], "mean_gain": round(v[1] / v[0], 4)} for k, v in self.op_stats.items()},
            "candidates": [{"id": i.cand_id, "parent_ids": i.parent_ids, "strategy_id": i.strategy_id, "op": i.op,
                            "fitness": i.fitness, "verdict": i.verdict} for i in evaluated],
        })
        return self.best_fitness - prev_best >= self.cfg.min_improvement

    def _should_stop(self, evaluated: list[Individual]) -> str | None:
        if any(i.verdict == "verified_success" for i in evaluated):
            return "verified_flag"
        if self.ctl.cancel.is_set():
            return "cancelled"
        if self.stop_reason:
            return self.stop_reason
        if self._remaining() < self.cfg.trials:
            return "budget_exhausted"
        if self._time_up():
            return "time_limit"
        if self.generation + 1 >= self.cfg.max_generations:
            return "max_generations"
        if self._stale >= self.cfg.patience:
            return "no_improvement"
        return None

    # -- main loop --------------------------------------------------------
    async def run(self) -> None:
        try:
            self._load_llm()
            self._persist("running")
            if not self.archive and self.generation == 0 and not self.history:
                drafts = await self._initial_population()
            else:
                drafts = []
            while True:
                if not drafts:
                    if not self.archive:
                        self.stop_reason = "search_exhausted"
                        break
                    drafts = self._make_children(self.cfg.population_size - min(self.cfg.elite, len(self.archive)))
                    if self.llm:
                        await self._llm_reword(drafts)
                    if not drafts:
                        self.stop_reason = "search_exhausted"
                        break
                with session_scope() as db:
                    saved = [save_draft(db, self.challenge_id, d, owner_id=self.owner_id, run_id=self.run_id) for d in drafts]
                inds = [Individual(s.id, s.text, s.strategy_id, s.parent_ids, self.generation, d.method, d.provenance.get("op"),
                                   d.provenance.get("parent_fitness")) for s, d in zip(saved, drafts)]
                inds = await self._approval_gate(inds)
                if inds is None:
                    self.stop_reason = "cancelled"
                    break
                await self._evaluate(inds)
                improved = self._record_generation(inds)
                self._stale = 0 if improved else self._stale + 1
                self._persist()
                reason = self._should_stop([i for i in inds if i.fitness is not None])
                if reason:
                    self.stop_reason = reason
                    break
                self.generation += 1
                drafts = []
        except asyncio.CancelledError:
            self.stop_reason = "cancelled"
        except PromptForgeError as e:
            self.stop_reason = f"failed: {e}"
        except Exception as e:  # noqa: BLE001
            log.exception("optimisation run crashed")
            self.stop_reason = f"failed: {type(e).__name__}"
        finally:
            failed = (self.stop_reason or "").startswith("failed")
            state = "failed" if failed else "cancelled" if self.stop_reason == "cancelled" else "completed"
            self._persist(state, stop_reason=self.stop_reason, pending_approval=None)
            _controllers.pop(self.run_id, None)


# -- public API ------------------------------------------------------------

def create_run(challenge_id: str, target_id: str | None, owner_id: str | None, config: dict[str, Any]) -> str:
    cfg = OptimizerConfig.from_dict(config)
    with session_scope() as db:
        c = get_challenge(db, challenge_id)
        if "api" not in c.allowed_methods:
            raise ValidationFailed("This challenge does not allow API testing; use manual mode")
        tid = target_id or c.target_id or "t_simulated"
        t = db.get(orm.Target, tid)
        if t is None:
            raise NotFound("Target not found")
        if t.kind == "manual":
            raise ValidationFailed("Optimisation needs an interactive target; manual targets are driven from the UI")
        if not t.enabled:
            raise ValidationFailed(f"Target '{t.name}' is disabled")
        run = orm.OptimizationRun(challenge_id=challenge_id, target_id=tid, owner_id=owner_id, config=asdict(cfg), state="pending")
        db.add(run)
        db.flush()
        return run.id


def start_run(run_id: str, transport=None) -> asyncio.Task:
    engine = OptimizationEngine(run_id, transport)
    task = asyncio.create_task(engine.run(), name=f"optimise-{run_id}")
    engine.ctl.task = task
    return task


def pause_run(run_id: str) -> None:
    ctl = _controllers.get(run_id)
    if not ctl:
        raise ValidationFailed("Run is not active")
    ctl.running.clear()
    _set_run(run_id, state="paused")


def resume_run(run_id: str) -> None:
    ctl = _controllers.get(run_id)
    if not ctl:
        raise ValidationFailed("Run is not active in this process")
    ctl.running.set()
    _set_run(run_id, state="running")


def cancel_run(run_id: str) -> None:
    ctl = _controllers.get(run_id)
    if not ctl:
        raise ValidationFailed("Run is not active")
    ctl.cancel.set()
    ctl.running.set()       # release any pause wait so it can exit
    ctl.decision.set()


def approve_generation(run_id: str, approved_ids: list[str] | None, reject: bool = False) -> None:
    ctl = _controllers.get(run_id)
    if not ctl:
        raise ValidationFailed("Run is not active")
    ctl.approved_ids, ctl.rejected = approved_ids, reject
    ctl.decision.set()


def mark_interrupted_runs() -> int:
    """Called at startup: runs that were mid-flight when the process died cannot continue silently."""
    with session_scope() as db:
        rows = db.scalars(select(orm.OptimizationRun).where(orm.OptimizationRun.state.in_(["running", "paused", "awaiting_approval", "pending"]))).all()
        for r in rows:
            r.state, r.stop_reason, r.pending_approval = "interrupted", "process restarted", None
        return len(rows)


def resume_interrupted(run_id: str, transport=None) -> asyncio.Task:
    """Continue an interrupted run from its persisted candidates/fitness (attempt budget carries over)."""
    with session_scope() as db:
        r = db.get(orm.OptimizationRun, run_id)
        if r is None:
            raise NotFound("Run not found")
        if r.state != "interrupted":
            raise ValidationFailed("Only interrupted runs can be resumed this way")
        r.state, r.stop_reason = "pending", None
        cands = db.scalars(select(orm.Candidate).where(orm.Candidate.run_id == run_id)).all()
    engine = OptimizationEngine(run_id, transport)
    for c in cands:
        p = c.provenance or {}
        if p.get("fitness") is not None:
            engine.archive.append(Individual(c.id, c.text, c.strategy_id, c.parent_ids, c.generation, c.method, p.get("op"),
                                             p.get("parent_fitness"), p["fitness"], p.get("components", {}), p.get("verdict"),
                                             experiment_id=p.get("experiment_id")))
            engine.tested_texts.append(c.text)
    if engine.history:
        engine.generation += 1
    task = asyncio.create_task(engine.run(), name=f"optimise-{run_id}")
    engine.ctl.task = task
    return task
