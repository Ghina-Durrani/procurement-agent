"""Shared FastAPI dependencies: database session and the current user.

Login is not designed yet (D-011, Q-004). Until it is, `get_current_user` is a
development-only stand-in (D-058): it loads the active user whose email is in the
DEMO_USER_EMAIL setting. Outside development it refuses every call, so the stand-in can
never act as a real login. For testing the review workflow (D-065) the frontend's user
switcher may send `X-Demo-User: <email>` to act as another active user of the same demo
organization; outside development every call is refused before the header is read. Real authentication replaces this one function; endpoints and
services only ever see a `User`, and take the organization from it, never from the client.
"""
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import Unauthenticated
from app.db.session import get_db
from app.models import Organization, User
from app.services.intake.llm import IntakeLLM, build_intake_llm


def db_session() -> Iterator[Session]:
    # A separate name lets tests swap the session without touching app.db.session.
    yield from get_db()


DbSession = Annotated[Session, Depends(db_session)]


def _active_user(db: Session, email: str) -> User | None:
    return db.scalars(
        select(User)
        .join(Organization, Organization.id == User.organization_id)
        .where(User.email == email, User.is_active, Organization.is_active)
    ).one_or_none()


def get_current_user(
    db: DbSession, x_demo_user: Annotated[str | None, Header()] = None
) -> User:
    settings = get_settings()
    if settings.app_env != "development":
        raise Unauthenticated("Login is not available yet.")
    email = (settings.demo_user_email or "").strip().lower()
    if not email:
        raise Unauthenticated("No demo user is configured (DEMO_USER_EMAIL).")
    user = _active_user(db, email)
    if user is None:
        raise Unauthenticated("The configured demo user does not exist or is inactive.")
    if x_demo_user is None:
        return user
    # Dev user switcher: only another active user of the demo user's own organization.
    other = _active_user(db, x_demo_user.strip().lower())
    if other is None or other.organization_id != user.organization_id:
        raise Unauthenticated("Unknown demo user.")
    return other


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_intake_llm() -> IntakeLLM:
    # One place picks fake or live (EXTRACTION_MODE, D-059); tests replace this dependency.
    return build_intake_llm()


IntakeAI = Annotated[IntakeLLM, Depends(get_intake_llm)]
