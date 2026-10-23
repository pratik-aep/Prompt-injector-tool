#!/usr/bin/env bash
# Start the backend (and the dashboard it serves) on 127.0.0.1 only.
#   scripts/start.sh          -> http://127.0.0.1:8000  (built dashboard + API)
#   scripts/start.sh --dev    -> API on :8000 plus Vite dev server on http://127.0.0.1:5173
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/run
[ -x .venv/bin/python ] || { echo "Run scripts/setup.sh first"; exit 1; }

if [ -f data/run/backend.pid ] && kill -0 "$(cat data/run/backend.pid)" 2>/dev/null; then
  echo "Backend already running (pid $(cat data/run/backend.pid))"
else
  nohup .venv/bin/python -m backend serve --host 127.0.0.1 --port "${PROMPTFORGE_PORT:-8000}" > data/run/backend.log 2>&1 &
  echo $! > data/run/backend.pid
  for _ in $(seq 1 40); do
    curl -fs "http://127.0.0.1:${PROMPTFORGE_PORT:-8000}/api/health" >/dev/null 2>&1 && break
    sleep 0.25
  done
  curl -fs "http://127.0.0.1:${PROMPTFORGE_PORT:-8000}/api/health" >/dev/null || { echo "Backend failed to start; see data/run/backend.log"; exit 1; }
  echo "Backend up: http://127.0.0.1:${PROMPTFORGE_PORT:-8000}  (log: data/run/backend.log)"
fi

if [ "${1:-}" = "--dev" ]; then
  if [ -f data/run/frontend.pid ] && kill -0 "$(cat data/run/frontend.pid)" 2>/dev/null; then echo "Vite already running"; else
    (cd frontend && nohup npm run dev > ../data/run/frontend.log 2>&1 & echo $! > ../data/run/frontend.pid)
    echo "Dev dashboard: http://127.0.0.1:5173"
  fi
fi
