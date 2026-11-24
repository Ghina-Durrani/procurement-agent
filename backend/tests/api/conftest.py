"""Fixtures for the API tests: the real app, the real migrations, one rolled-back transaction.

The test database fixtures are reused from tests/db, so these tests also need PostgreSQL
(marker `integration`). Each test acts as a user it creates, through the same
development-only stand-in the running app uses (D-058).
"""
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_intake_llm
from app.config import get_settings
from app.main import create_app
from app.models import User
from app.services.extraction import FakeLLMClient
from app.services.intake.llm import IntakeLLM

TEST_AI_LABEL = "fake (test)"


class ScriptedAI:
    """The AI the app uses in API tests. Script its replies; with none left, a call fails."""

    def __init__(self) -> None:
        self.client = FakeLLMClient([])

    def script(self, *replies: str | Exception) -> FakeLLMClient:
        self.client = FakeLLMClient(replies)
        return self.client

    def intake(self) -> IntakeLLM:
        return IntakeLLM(self.client, TEST_AI_LABEL)


@pytest.fixture()
def ai() -> ScriptedAI:
    return ScriptedAI()
from tests.db.conftest import engine, session  # noqa: F401 - pytest fixtures used below


@pytest.fixture()
def client(
    session: Session, monkeypatch: pytest.MonkeyPatch, ai: ScriptedAI  # noqa: F811
) -> Iterator[TestClient]:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("DEMO_USER_EMAIL", raising=False)
    get_settings.cache_clear()
    app = create_app()

    def _session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[db_session] = _session
    app.dependency_overrides[get_intake_llm] = ai.intake  # never the real model in tests
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


@pytest.fixture()
def act_as(monkeypatch: pytest.MonkeyPatch) -> Callable[[User], None]:
    """Make every following API call act as this user."""

    def _act_as(user: User) -> None:
        monkeypatch.setenv("DEMO_USER_EMAIL", user.email)
        get_settings.cache_clear()

    return _act_as
