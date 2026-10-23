# PromptForge

A local, modular platform for **authorized** prompt-injection CTF practice and competition work:
create challenges, generate candidate prompts from a strategy library, test them against a local
Ollama model / a registered CTF endpoint / a manual copy-paste workflow, evaluate with
deterministic checks, and run a feedback-driven optimizer under a hard query budget.

Everything runs on one Mac, binds to `127.0.0.1`, and needs no paid service.

## Quick start (macOS, Apple Silicon)

```bash
cd promptforge
scripts/setup.sh        # venv + deps + dashboard build + database (Python 3.11+, Node optional)
scripts/start.sh        # http://127.0.0.1:8000  (dashboard + API)
scripts/stop.sh         # shutdown
scripts/test.sh         # all automated tests
scripts/e2e_smoke.sh    # live smoke test of the running backend (simulator only)
```
Developer mode with hot reload: `scripts/start.sh --dev` → http://127.0.0.1:5173.

### Local model (optional)
Install Ollama (https://ollama.com), run `ollama serve`, then pull a small model yourself, e.g.
`ollama pull llama3.2:3b` (~2 GB). PromptForge detects it on **Targets → Use this model**; it never downloads models.
Local concurrency defaults to 1 so only one inference runs at a time on a 16 GB machine.

### Without any model
The built-in **Local simulator** target is a deterministic rule-based "vulnerable defender" (not an LLM) that lets you
exercise the whole pipeline and run the practice challenges offline.

## Workflow
1. **Targets** – register an Ollama model, an authorized HTTP endpoint, or use Manual.
2. **Challenge Workspace** – pick/create a challenge (7 built-in practice challenges: secret extraction ×3, instruction hierarchy, format enforcement, indirect injection, tool-output trust).
3. **Prompt Studio** – generate variants (template / AI / hybrid / manual), edit, compare, run a test, or paste a response from an external chatbot.
4. **Optimization Lab** – population search with mutation, lineage, budget, pause/resume/cancel, optional per-generation approval.
5. **Response Analyzer / History / Analytics** – inspect, annotate, filter, compare, export (JSON/CSV), import teammates' JSON.

CLI equivalents: `.venv/bin/python -m backend {init,serve,challenges,test,manual,generate,optimize,export,backup}`.

## Verdicts (what counts as success)
| Verdict | Meaning |
|---|---|
| `verified_success` | Deterministic evaluator matched ground truth (exact flag, regex, schema break, rule violation), or a human attested the competition's verifier accepted a flag |
| `possible_success` | Evidence but unverified: large partial flag leak, flag-shaped string from an external bot, or an AI-judge *estimate* |
| `failed` | Objective not met |
| `invalid_test` | Target error / empty response / cancelled – not a result |
| `evaluation_error` | Evaluator could not run |

A fabricated flag (`CTF{…}` that isn't the configured one) is never verified. Tone ("Sure, happy to help!") earns no score.

## Security model
- Loopback bind only; non-loopback refused unless `PROMPTFORGE_ALLOW_LAN=1`. Host-header allowlist (DNS rebinding) and cross-origin write blocking.
- Remote targets must be registered and enabled; URLs validated (http/https, no embedded credentials, private/loopback/link-local/metadata addresses rejected unless the target is explicitly flagged local); re-validated at call time; redirects not followed. No discovery or scanning exists.
- Credentials are references (`env:NAME`, `keychain:SERVICE`), never stored in SQLite; resolved secrets are scrubbed from logs/errors.
- Expected flags and defender prompts live only in server-side challenge config; public challenge views, generators (including the LLM) and exports never include them (sweep-tested over all GET endpoints).
- Attacker text is always `role: user`. Model output is rendered as plain text and never executed, never touches config or files. CSV export neutralises formula injection. Evaluator plugins run arbitrary Python and are off unless `PROMPTFORGE_ENABLE_PLUGINS=1`.
- Rate limiting per remote target, per-challenge query budget enforced atomically (including under concurrency).

## Configuration (env vars, prefix `PROMPTFORGE_`)
`HOST`, `PORT`, `DB_PATH`, `OLLAMA_URL`, `LOCAL_CONCURRENCY` (1), `TIMEOUT_S`, `ENABLE_PLUGINS`, `ALLOW_LAN`, `CHALLENGES_DIR`, `STRATEGIES_DIR`, `PLUGINS_DIR`.

More: [documentation/ARCHITECTURE.md](documentation/ARCHITECTURE.md), [documentation/EXAMPLE_EXPERIMENT.md](documentation/EXAMPLE_EXPERIMENT.md), [documentation/TEST_REPORT.md](documentation/TEST_REPORT.md).
