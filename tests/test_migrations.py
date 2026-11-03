"""The migrations must build exactly the schema the models describe, both ways."""
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401
from app import migrate
from app.database import Base


def fresh_engine(tmp_path, name="m.db"):
    return create_engine(f"sqlite:///{tmp_path / name}")


def version(engine):
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def schema_diff(engine):
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        return compare_metadata(ctx, Base.metadata)


def test_upgrade_builds_the_model_schema(tmp_path):
    engine = fresh_engine(tmp_path)
    migrate.upgrade(engine)
    assert version(engine) == "0001"
    # Empty diff = a model change without a matching migration would fail here.
    assert schema_diff(engine) == []


def test_downgrade_to_base_removes_everything(tmp_path):
    engine = fresh_engine(tmp_path)
    migrate.upgrade(engine)
    cfg = migrate.alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        from alembic import command

        command.downgrade(cfg, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}


def test_pre_migration_database_is_stamped_not_recreated(tmp_path):
    # A database made by the old create_all() startup, with data in it.
    engine = fresh_engine(tmp_path)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO users (email, password_hash, created_at) VALUES ('a@b.c', 'x', '2026-01-01')"
        )
    migrate.upgrade(engine)
    assert version(engine) == "0001"
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM users").scalar() == 1


def test_upgrade_is_idempotent(tmp_path):
    engine = fresh_engine(tmp_path)
    migrate.upgrade(engine)
    migrate.upgrade(engine)
    assert version(engine) == "0001"
