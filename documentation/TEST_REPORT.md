# Test & verification report

Run `scripts/test.sh` to reproduce.

## Automated (all passing when last run)
- Backend pytest: **118 tests** – security/SSRF/redaction, evaluators, generation/dedupe/diversity, strategies CRUD/import/export,
  mutations, fitness, Ollama adapter (mocked streaming/errors/timeouts), HTTP-API adapter (mapping, auth, retries, rate limit, credential scrubbing),
  OpenAI/Anthropic adapters (mocked), runner (persistence, budget incl. concurrency, duplicates, trials, roles, multi-turn, sessions/branching,
  cancellation, adapter crash), manual workflow + flag confirmation, optimizer (flag found, hard-challenge lineage, budget/time/patience/max-gen stops,
  cancel, pause/resume, approval gate, failure recovery, interrupted-run resume, concurrency), API (CRUD, scope rules, secret-leak sweep, host/origin guard, export/import, analytics), full E2E scenario.
- Frontend: TypeScript type-check clean; **27 vitest component tests** (create challenge, model selection, target registration, prompt editing, generate, run, manual submit, copy, optimizer start/pause/cancel/approve, analyzer, history filters/compare, empty-state honesty, shortcuts, backend-down error).

## Live verification on this Mac (Apple Silicon, Python 3.12, Node 26)
- Backend and built dashboard served on 127.0.0.1:8000; SPA routes, Host-header rejection (403) confirmed.
- `scripts/e2e_smoke.sh` against the running server: generate → test → optimise (completed, verified flag) → analytics.
- Real Ollama (`qwen3.5-9b-aggressive`, already installed; nothing downloaded): health check, single attempt (exact flag verified, latency + token counts recorded),
  3-candidate optimizer run incl. multi-turn candidate (verified in generation 0), live cancel.

## Not verified / known limitations
- **No visual/browser check** of the dashboard was possible in this session (no browser automation endpoint); layout/responsiveness is untested by eye. Component tests and a production build pass.
- The HTTP-API adapter, OpenAI and Anthropic adapters were tested only against mocked transports – no real competition endpoint or paid API was contacted.
- macOS Keychain lookup (`keychain:` refs) is implemented but untested.
- The optimizer's learning signal is weak when a target gives no partial-progress signal (all failures score 0): on the simulated *hard* challenge, 9/12 seeds find the flag within 60 queries (patience 5). Against real LLMs, results depend on the model.
- The practice challenges evaluated on small/uncensored models are easy; the simulator is a mock, not a measure of model robustness.
- Constraint "refusal context" detection is heuristic (keyword-based); a model quoting a forbidden word in a non-refusal way can false-positive.
- Evaluator plugins execute arbitrary Python (opt-in, no sandbox). The API has no authentication (localhost-only by design).
- LAN mode (`PROMPTFORGE_ALLOW_LAN=1`) disables host/origin protections and is unauthenticated – use only on a trusted network.
