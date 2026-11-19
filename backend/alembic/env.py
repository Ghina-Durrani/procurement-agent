"""Alembic environment: tells Alembic which database to use and what the models look like.

The connection comes from app.db.session (which reads the POSTGRES_* settings), so the
app and the migrations always use the same database and no password appears here.
"""
from logging.config import fileConfig

from alembic import context

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base
from app.db.session import get_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    with get_engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    # Offline mode would need a connection string built by hand, which the Backend Guide
    # forbids. Run migrations against the database instead.
    raise RuntimeError("Offline migrations are not supported. Run 'alembic upgrade head'.")
run_migrations_online()
