
"""Database connection and session management."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create and reuse the database engine."""
    return create_engine(
        get_settings().build_database_url(),
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Create and reuse the session factory."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Iterator[Session]:
    """Provide a database session and close it afterward."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def check_connection() -> bool:
    """Check whether PostgreSQL responds to a simple query."""
    with get_engine().connect() as connection:
        return connection.execute(text("SELECT 1")).scalar() == 1
