"""Alembic environment. The database URL comes from the app's settings (DATABASE_URL),
so the CLI and the app always agree on which database they are talking to."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

import app.models  # noqa: F401  (registers the tables on Base.metadata)
from app.config import get_settings
from app.database import Base

target_metadata = Base.metadata

# Only the CLI configures logging from alembic.ini; inside the app, leave uvicorn's alone.
if context.config.config_file_name and "connection" not in context.config.attributes:
    fileConfig(context.config.config_file_name)


def run_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    # app/migrate.py passes in a connection it already holds (and has locked);
    # the alembic CLI does not, so build an engine from settings.
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        _run(conn)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite can't ALTER most things in place; batch mode copies the table instead.
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
