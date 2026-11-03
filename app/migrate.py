"""Bring the database schema up to date with Alembic. Runs at app startup.

- Fresh database: applies every migration.
- Database created before migrations existed (tables, but no recorded revision):
  stamps it at the baseline revision, then applies anything newer. Nothing is
  re-created and no data is touched.
- On Postgres, a transaction-level advisory lock makes concurrent instances
  migrate one at a time; the others wait, then find nothing left to do.

CLI equivalent (same URL, from DATABASE_URL):  alembic upgrade head
"""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

log = logging.getLogger("uvicorn.error")

ROOT = Path(__file__).resolve().parent.parent
BASELINE = "0001"
# Arbitrary app-wide key for pg_advisory_xact_lock.
LOCK_KEY = 7_302_118


def alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def upgrade(engine: Engine, revision: str = "head") -> None:
    cfg = alembic_config()
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
        cfg.attributes["connection"] = conn

        # No revision recorded covers both a missing and an empty alembic_version table.
        unversioned = MigrationContext.configure(conn).get_current_revision() is None
        if unversioned and inspect(conn).has_table("users"):
            log.info("Existing schema without migration history: stamping %s", BASELINE)
            command.stamp(cfg, BASELINE)

        command.upgrade(cfg, revision)
