#!/usr/bin/env sh
# Run the API locally (Git Bash / Linux / macOS). Uses DATABASE_URL from ../.env (SQLite fallback when empty).
cd "$(dirname "$0")"
export MPLBACKEND=Agg
PY=.venv/Scripts/python.exe; [ -x "$PY" ] || PY=.venv/bin/python
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8200}"
