"""Fixtures for the database tests.

They build a separate test database (named <POSTGRES_DB>_test) with the real Alembic
migrations, so the tests check exactly what production will get. The tests wipe that
database, never the development one.
"""
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_engine, get_session_factory

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _clear_caches() -> None:
    for cached in (get_settings, get_engine, get_session_factory):
        cached.cache_clear()


def _create_test_database_if_missing(name: str) -> None:
    admin_url = get_settings().build_database_url().set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            ).scalar()
            if not exists:
                # CREATE DATABASE cannot take a bound parameter. The name comes from our own
                # settings plus "_test", never from user input, and is quoted safely.
                quoted = admin.dialect.identifier_preparer.quote(name)
                connection.execute(text(f"CREATE DATABASE {quoted}"))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    _clear_caches()
    development_name = get_settings().postgres_db
    test_name = (
        development_name if development_name.endswith("_test") else f"{development_name}_test"
    )
    _create_test_database_if_missing(test_name)

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("POSTGRES_DB", test_name)
        _clear_caches()
        test_engine = get_engine()
        # Safety: this fixture deletes every table, so refuse anything not named *_test.
        assert test_engine.url.database == test_name and test_name.endswith("_test")
        with test_engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        command.upgrade(Config(str(ALEMBIC_INI)), "head")
        try:
            yield test_engine
        finally:
            test_engine.dispose()
    _clear_caches()


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    """Each test runs inside a transaction that is rolled back, so tests stay independent."""
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield db
    finally:
        db.close()
        outer.rollback()
        connection.close()
