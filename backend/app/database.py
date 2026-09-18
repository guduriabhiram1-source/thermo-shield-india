"""SQLAlchemy engine / session management with PostGIS support.

Latitude/longitude are stored as plain columns so the ORM works on SQLite for
local development and tests; on PostgreSQL every spatial table additionally
gets a `geom geography(Point,4326)` column, a GIST index and a trigger that
keeps it in sync with latitude/longitude (see `ensure_geometry_columns`)."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

log = logging.getLogger("thermoshield.db")


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = settings.effective_database_url

    # SQLite for local development and tests
    if url.startswith("sqlite"):
        eng = create_engine(
            url,
            connect_args={
                "check_same_thread": False,
                "timeout": 60,
            },
            future=True,
        )

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return eng

    # PostgreSQL using psycopg 3
    # Your requirements.txt contains `psycopg` and `psycopg-binary`,
    # so explicitly tell SQLAlchemy to use the psycopg driver.
    if url.startswith("postgresql://"):
        url = url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        future=True,
    )


engine = _make_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=True,
    autocommit=False,
    expire_on_commit=False,
)

IS_POSTGRES = engine.dialect.name.startswith("postgres")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


GEO_TABLES = [
    "thermal_detections",
    "thermal_events",
    "industrial_facilities",
    "refineries",
    "power_plants",
    "mines",
    "gas_facilities",
    "roads",
    "land_cover",
    "population",
    "historical_events",
    "affected_areas",
    "weather_observations",
]


def init_db() -> None:
    """Create extension / tables / spatial indexes (idempotent).

    Alembic migrations are provided for production; `init_db` keeps
    development and tests simple.
    """

    from . import models  # noqa: F401  (register mappings)

    if IS_POSTGRES:
        with engine.begin() as conn:
            conn.execute(
                text("CREATE EXTENSION IF NOT EXISTS postgis")
            )

    Base.metadata.create_all(engine)

    if IS_POSTGRES:
        ensure_geometry_columns()

    log.info(
        "Database ready (%s)",
        "PostgreSQL/PostGIS"
        if IS_POSTGRES
        else "SQLite development fallback",
    )


def ensure_geometry_columns() -> None:
    with engine.begin() as conn:
        for table in GEO_TABLES:

            # Add PostGIS geography column
            conn.execute(
                text(
                    f"ALTER TABLE {table} "
                    f"ADD COLUMN IF NOT EXISTS "
                    f"geom geography(Point, 4326)"
                )
            )

            # Create spatial index
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS "
                    f"idx_{table}_geom "
                    f"ON {table} USING GIST (geom)"
                )
            )

            # Create function to keep geometry synchronized
            # with latitude / longitude.
            conn.execute(
                text(
                    f"""
                    CREATE OR REPLACE FUNCTION {table}_sync_geom()
                    RETURNS trigger AS $$
                    BEGIN
                        IF NEW.latitude IS NOT NULL
                           AND NEW.longitude IS NOT NULL THEN

                            NEW.geom :=
                                ST_SetSRID(
                                    ST_MakePoint(
                                        NEW.longitude,
                                        NEW.latitude
                                    ),
                                    4326
                                )::geography;

                        END IF;

                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )
            )

            # Remove old trigger if it exists
            conn.execute(
                text(
                    f"DROP TRIGGER IF EXISTS "
                    f"trg_{table}_geom ON {table}"
                )
            )

            # Create geometry synchronization trigger
            conn.execute(
                text(
                    f"""
                    CREATE TRIGGER trg_{table}_geom
                    BEFORE INSERT OR UPDATE
                    ON {table}
                    FOR EACH ROW
                    EXECUTE FUNCTION {table}_sync_geom()
                    """
                )
            )

            # Populate geometry for existing rows
            conn.execute(
                text(
                    f"""
                    UPDATE {table}
                    SET geom =
                        ST_SetSRID(
                            ST_MakePoint(
                                longitude,
                                latitude
                            ),
                            4326
                        )::geography
                    WHERE geom IS NULL
                      AND latitude IS NOT NULL
                      AND longitude IS NOT NULL
                    """
                )
            )
