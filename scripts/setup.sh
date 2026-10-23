#!/usr/bin/env bash
# One-time setup: Python venv, backend deps, frontend deps, database. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=""
for c in python3.12 python3.13 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "Python 3.11+ is required (brew install python@3.12)"; exit 1; }
echo "Using $($PY --version) at $(command -v $PY)"

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

if command -v npm >/dev/null 2>&1; then
  (cd frontend && npm install --no-audit --no-fund && npm run build)
else
  echo "Node/npm not found: skipping the dashboard build (the API and CLI still work)."
fi

.venv/bin/python -m backend init
if command -v ollama >/dev/null 2>&1; then
  echo "Ollama found. Installed models:"; ollama list 2>/dev/null || echo "  (server not running: start it with 'ollama serve')"
else
  echo "Ollama not installed (optional): https://ollama.com/download"
fi
echo "Setup complete. Start with: scripts/start.sh"
