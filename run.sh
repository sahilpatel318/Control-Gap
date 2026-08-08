#!/usr/bin/env bash
# Convenience script: set up the backend, seed the registers, and start the API.
# The frontend is started separately (see README): cd frontend && npm install && npm run dev
set -euo pipefail
cd "$(dirname "$0")/backend"

if [ ! -d .venv ]; then
  echo "[run] creating virtualenv…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[run] installing core requirements…"
pip install -q -r requirements.txt

# Load .env if present (optional LLM key). Never fails if absent.
if [ -f ../.env ]; then
  echo "[run] found ../.env — exporting variables"
  set -a; # shellcheck disable=SC1091
  source ../.env; set +a
fi

echo "[run] seeding gap registers…"
python seed.py

echo "[run] starting API on http://localhost:8000  (Ctrl+C to stop)"
exec uvicorn app.main:app --reload --port 8000
