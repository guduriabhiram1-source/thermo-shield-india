"""CLI: pull the latest FIRMS data now (same code path as the scheduler).  python scripts/ingest_firms.py"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ.setdefault("MPLBACKEND", "Agg")

from app.database import init_db  # noqa: E402
from app.services import ingest_service  # noqa: E402

if __name__ == "__main__":
    init_db()
    print(ingest_service.live_ingest("cli"))
