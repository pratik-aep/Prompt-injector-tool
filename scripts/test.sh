#!/usr/bin/env bash
# Run every automated test: backend (pytest), frontend type-check + component tests.
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m pytest -q
(cd frontend && npx tsc --noEmit && npx vitest run)
