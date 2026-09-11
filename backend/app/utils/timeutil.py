from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..config import HISTORY_LIMIT

IST = timezone(timedelta(hours=5, minutes=30))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; normalise everything to aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    dt = ensure_utc(dt)
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def fmt_ist(dt: datetime | None) -> str:
    dt = ensure_utc(dt)
    return dt.astimezone(IST).strftime("%d %b %Y %H:%M IST") if dt else "Unavailable"


def fmt_utc(dt: datetime | None) -> str:
    dt = ensure_utc(dt)
    return dt.strftime("%d %b %Y %H:%M UTC") if dt else "Unavailable"


def history_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """The dynamically calculated one-year window the platform may serve."""
    now = now or utcnow()
    return now - HISTORY_LIMIT, now


def clamp_to_history(start: datetime | None, end: datetime | None, now: datetime | None = None) -> tuple[datetime, datetime]:
    lo, hi = history_window(now)
    s = ensure_utc(start) or lo
    e = ensure_utc(end) or hi
    s = max(s, lo)
    e = min(e, hi)
    if s > e:
        s = e
    return s, e
