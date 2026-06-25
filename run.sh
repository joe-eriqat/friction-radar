#!/usr/bin/env bash
# Launch Friction Radar locally.
#   ./run.sh            # http://127.0.0.1:8080
#   HOST=0.0.0.0 PORT=9000 ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d venv ]]; then
  echo "venv/ not found. Create it first:"
  echo "  python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
  exit 1
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
exec ./venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT" "$@"
