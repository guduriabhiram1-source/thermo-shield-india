"""Initial schema: all tables from the ORM metadata + PostGIS geography columns, GIST indexes and sync triggers.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.database import Base, GEO_TABLES
from app import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name.startswith("postgres"):
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    Base.metadata.create_all(bind)
    if bind.dialect.name.startswith("postgres"):
        for table in GEO_TABLES:
            op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS geom geography(Point, 4326)")
            op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_geom ON {table} USING GIST (geom)")
            op.execute(f"""
                CREATE OR REPLACE FUNCTION {table}_sync_geom() RETURNS trigger AS $$
                BEGIN
                    IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
                        NEW.geom := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326)::geography;
                    END IF;
                    RETURN NEW;
                END; $$ LANGUAGE plpgsql;
            """)
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_geom ON {table}")
            op.execute(f"CREATE TRIGGER trg_{table}_geom BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION {table}_sync_geom()")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name.startswith("postgres"):
        for table in GEO_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_geom ON {table}")
            op.execute(f"DROP FUNCTION IF EXISTS {table}_sync_geom()")
    Base.metadata.drop_all(bind)
