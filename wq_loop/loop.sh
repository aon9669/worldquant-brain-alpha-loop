#!/bin/bash
# MacBook M1 supervisor for the WorldQuant loop (moved from the Linux box on 2026-11-08). Run by launchd (com.aon.wqloop).
set -uo pipefail
umask 077
W="${WQ_HOME:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$W"
export PATH="$W/venv/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
WQ_ENV_FILE="${WQ_ENV_FILE:-$HOME/.wq_env}"
[ -f "$WQ_ENV_FILE" ] && . "$WQ_ENV_FILE"
for key in WQB_EMAIL WQB_PASSWORD; do
  if [ -z "${!key:-}" ]; then echo "$key missing; not started"; sleep 600; exit 1; fi
done
printf '%s\n' "$$" > wq_loop/loop.pid
trap 'exit 0' TERM INT
while true; do
  started=$(date +%s)
  python3 wq_loop/engine.py
  rc=$?
  elapsed=$(( $(date +%s) - started ))
  if [ "$rc" = 30 ]; then delay=1800
  elif [ "$rc" = 75 ]; then delay=30
  else delay=$((300-elapsed)); fi
  if ((delay>0)); then sleep "$delay" & wait $! || true; fi
done
