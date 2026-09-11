"""FIRMS provider adapter interface."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class FeedResult:
    rows: list[dict] = field(default_factory=list)
    status: dict[str, str] = field(default_factory=dict)
    provider: str = ""
    mode: str = "live"  # live | archive


class FirmsProvider:
    name = "base"

    def configured(self) -> bool:  # pragma: no cover - interface
        return False

    def fetch_latest(self) -> FeedResult:  # pragma: no cover - interface
        raise NotImplementedError

    def fetch_archive(self, start: date, end: date) -> FeedResult:  # pragma: no cover - interface
        raise NotImplementedError
