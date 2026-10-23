"""PromptForge command line: init, serve, challenges, test, generate, optimize, export."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy import select

from .core.config import get_settings
from .database import orm
from .database.session import session_scope
from .experiments.candidates import save_draft
from .experiments.runner import run_candidate, submit_manual
from .generators.base import GenerationRequest
from .generators.service import generate_candidates
from .optimizer.engine import create_run, start_run
from .services import challenges as chs
from .services import exports
from .services.bootstrap import bootstrap


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_init(_a):
    bootstrap()
    print(f"Database ready at {get_settings().db_path}")


def cmd_serve(a):
    import uvicorn
    s = get_settings()
    host = a.host or s.host
    if host not in ("127.0.0.1", "localhost", "::1") and not s.allow_lan:
        sys.exit("Refusing to bind to a non-loopback address. Set PROMPTFORGE_ALLOW_LAN=1 to opt in to LAN access.")
    uvicorn.run("backend.api.app:create_app", factory=True, host=host, port=a.port or s.port, log_level="info")


def cmd_challenges(_a):
    bootstrap()
    with session_scope() as db:
        for c in db.scalars(select(orm.Challenge).order_by(orm.Challenge.difficulty)):
            v = chs.public_view(db, c)
            print(f"{v['id']:28} {v['difficulty']:7} {v['type']:22} {v['attempts_used']:>3}/{v['query_budget']:<4} {v['status']}")


def cmd_test(a):
    bootstrap()
    r = asyncio.run(run_candidate(a.challenge, a.prompt, trials=a.trials, target_id=a.target))
    _print({k: r[k] for k in ("experiment_id", "verdict", "score", "reasons", "response_text", "latency_ms", "success_rate", "queries_used")})


def cmd_manual(a):
    bootstrap()
    r = asyncio.run(submit_manual(a.challenge, a.prompt, a.response))
    _print({k: r[k] for k in ("experiment_id", "verdict", "score", "reasons")})


def cmd_generate(a):
    bootstrap()

    async def go():
        with session_scope() as db:
            pub = chs.public_view(db, chs.get_challenge(db, a.challenge))
            strategies = list(db.scalars(select(orm.Strategy)))
        drafts, warns = await generate_candidates(GenerationRequest(pub, mode="template", count=a.count), strategies)
        with session_scope() as db:
            for d in drafts:
                save_draft(db, a.challenge, d)
        for d in drafts:
            print(f"--- [{d.strategy_id}] ---\n{d.text}\n")
        for w in warns:
            print("warning:", w)
    asyncio.run(go())


def cmd_optimize(a):
    bootstrap()
    cfg = {"population_size": a.population, "max_generations": a.generations, "attempt_budget": a.budget, "seed": a.seed, "trials": a.trials}

    async def go():
        rid = create_run(a.challenge, a.target, None, cfg)
        await start_run(rid)
        return rid
    rid = asyncio.run(go())
    with session_scope() as db:
        r = db.get(orm.OptimizationRun, rid)
        print(f"run {rid}: {r.state} ({r.stop_reason}) generations={r.generation + 1} attempts={r.attempts_used} best_fitness={r.best_fitness}")
        for h in r.history:
            print(f"  gen {h['generation']}: best={h['best_fitness']} mean={h['mean_fitness']} verdicts={h['verdicts']}")


def cmd_export(a):
    bootstrap()
    with session_scope() as db:
        out = exports.export_csv(db, a.challenge) if a.format == "csv" else json.dumps(exports.export_json(db, a.challenge), indent=2)
    if a.out:
        open(a.out, "w").write(out)
        print(f"wrote {a.out}")
    else:
        print(out)


def cmd_backup(_a):
    bootstrap()
    print(exports.backup_database())


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="promptforge")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    s = sub.add_parser("serve"); s.add_argument("--host"); s.add_argument("--port", type=int); s.set_defaults(fn=cmd_serve)
    sub.add_parser("challenges").set_defaults(fn=cmd_challenges)
    t = sub.add_parser("test"); t.add_argument("challenge"); t.add_argument("prompt"); t.add_argument("--target"); t.add_argument("--trials", type=int, default=1); t.set_defaults(fn=cmd_test)
    m = sub.add_parser("manual"); m.add_argument("challenge"); m.add_argument("prompt"); m.add_argument("response"); m.set_defaults(fn=cmd_manual)
    g = sub.add_parser("generate"); g.add_argument("challenge"); g.add_argument("--count", type=int, default=6); g.set_defaults(fn=cmd_generate)
    o = sub.add_parser("optimize"); o.add_argument("challenge"); o.add_argument("--target"); o.add_argument("--population", type=int, default=6)
    o.add_argument("--generations", type=int, default=5); o.add_argument("--budget", type=int, default=30); o.add_argument("--seed", type=int); o.add_argument("--trials", type=int, default=1)
    o.set_defaults(fn=cmd_optimize)
    e = sub.add_parser("export"); e.add_argument("--format", choices=["json", "csv"], default="json"); e.add_argument("--challenge"); e.add_argument("--out"); e.set_defaults(fn=cmd_export)
    sub.add_parser("backup").set_defaults(fn=cmd_backup)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
