"""Which AI the app uses (D-059) and the CORS setting (Q-003). No database, no network."""
import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.evaluation.cases import Split, load_cases
from app.services.extraction import LLMNotConfigured, LLMRequestFailed
from app.services.extraction.prompt import build_user_message
from app.services.intake.llm import FAKE_MODEL_LABEL, build_intake_llm


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_fake_mode_is_the_default_and_is_labelled() -> None:
    llm = build_intake_llm(_settings())
    assert llm.label == FAKE_MODEL_LABEL


def test_fake_mode_echoes_a_verified_dev_case() -> None:
    case = next(c for c in load_cases(require_verified=True, split=Split.DEV) if c.case_id == "EV-009")
    reply = json.loads(build_intake_llm(_settings()).client.complete("x", build_user_message(case.request_text)))
    assert reply["delivery_deadline"]["status"] == "PRESENT"
    assert reply["estimated_total"]["status"] == "MISSING"


def test_fake_mode_fails_on_any_other_text() -> None:
    client = build_intake_llm(_settings()).client
    with pytest.raises(LLMRequestFailed):
        client.complete("x", build_user_message("Need 2 staplers"))


def test_fake_mode_never_answers_a_held_out_test_case() -> None:
    client = build_intake_llm(_settings()).client
    test_case = load_cases(require_verified=False, split=Split.TEST)[0]
    with pytest.raises(LLMRequestFailed):
        client.complete("x", build_user_message(test_case.request_text))


def test_live_mode_without_a_key_fails_without_calling_anyone() -> None:
    llm = build_intake_llm(_settings(extraction_mode="live", llm_api_key=None))
    with pytest.raises(LLMNotConfigured):
        llm.client.complete("x", "y")


def test_cors_allows_only_the_configured_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:5173"]')
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        headers = {"Access-Control-Request-Method": "POST"}
        allowed = client.options("/api/v1/requests", headers={**headers, "Origin": "http://localhost:5173"})
        assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
        other = client.options("/api/v1/requests", headers={**headers, "Origin": "http://evil.example"})
        assert "access-control-allow-origin" not in other.headers
    finally:
        get_settings.cache_clear()
