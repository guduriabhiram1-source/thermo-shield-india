"""CLI: historical FIRMS backfill (requires NASA_FIRMS_MAP_KEY; max 12 months; rows are HISTORICAL and never alert).
python scripts/backfill_firms.py 2026-06-01 2026-09-01"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ.setdefault("MPLBACKEND", "Agg")

from app.database import init_db  # noqa: E402
from app.services import ingest_service  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    init_db()
    start = date.fromisoformat(sys.argv[1])
    end = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else None
    print(ingest_service.backfill_archive(start, end, actor="cli"))
