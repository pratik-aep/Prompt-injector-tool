# Architecture

```
 React dashboard (frontend/)  ──HTTP /api──►  FastAPI (backend/api)  ── 127.0.0.1 only
                                                   │
        ┌──────────────┬───────────────┬───────────┴────────┬──────────────────┐
        ▼              ▼               ▼                    ▼                  ▼
   generators/     experiments/     optimizer/          services/          evaluators/
 template·ai·hybrid  runner         engine (GA +        challenges,        exact_flag, regex,
 dedupe/diversity   (budget,sessions, bandit ops)       targets, exports,  json_schema, constraint,
        │            persistence)   mutations, fitness  analytics          plugins, ai_judge(estimate)
        ▼              │                │
   strategies/         ▼                ▼
 (JSON in templates/)  targets/  ◄── same runner path for every attempt
                       ollama · http_api · manual · openai · anthropic · simulated
                                   │
                          database/ (SQLite, SQL migrations, SQLAlchemy ORM)
```

## Attempt pipeline (`experiments/runner.py`)
reserve budget (per-challenge lock, released before the network call) → build messages (system text only from trusted
challenge config; attacker text is `role=user`, wrapped by the challenge's `user_template`) → `Target.generate` →
pure `evaluate_response` → persist Response + Evaluation (+ VerifiedFlag on exact match) → session history.
Manual mode takes the same path minus the network call; external flags need human confirmation.

## Optimizer (`optimizer/engine.py`)
Gen 0: diverse template (or hybrid) population, strategies ordered by historical success on that challenge type.
Evaluate → `fitness = success + consistency + novelty − cost` (success = evaluator score only) → archive.
Next generation: elites carried over untested; children via tournament parent selection with per-strategy diversity
pressure and UCB bandit choice among mutation operators (reword, context, reorder, format, example, shorten, expand,
crossover/stacking, optional LLM reword) using observed gain over parent; near-duplicates rejected; lineage stored in
`candidates.parent_ids`. Stops on: verified flag, attempt budget, cancel, max generations, time limit, patience.
Optional per-generation human approval; pause/resume; interrupted runs (process restart) can be continued from DB.

## Data model
`team_members, targets, challenges, strategies, candidates, experiments, responses, evaluations, verified_flags,
conversation_sessions, optimization_runs, app_settings` (+`schema_migrations`). Migrations: `backend/database/migrations/NNN_*.sql`,
applied in order on startup. Backup: `POST /api/backup` (SQLite online backup).

## Extending
- **New target kind**: subclass `Target` in `backend/targets/`, register in `registry.py`.
- **New check**: add to `evaluators/checks.py` + `engine._run_check` (or write a plugin; see `configuration/evaluator_plugins/`).
- **New strategy**: add JSON to `templates/strategies/` or create it in the UI (templates, `{{vars}}`, `---TURN---` for multi-turn).
- **New challenge**: JSON in `challenges/` (see existing files) or create in the UI.
