#!/usr/bin/env bash
# Stop everything started by start.sh. Running optimisation runs are marked 'interrupted' and can be continued later.
cd "$(dirname "$0")/.."
for n in backend frontend; do
  f=data/run/$n.pid
  if [ -f "$f" ]; then
    pid=$(cat "$f")
    if kill -0 "$pid" 2>/dev/null; then pkill -P "$pid" 2>/dev/null; kill "$pid" 2>/dev/null && echo "Stopped $n (pid $pid)"; else echo "$n was not running"; fi
    rm -f "$f"
  fi
done
