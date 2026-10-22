from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def test_health_returns_ok():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_are_hidden_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()          # forget the old settings
    client = TestClient(create_app())
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    get_settings.cache_clear()          # leave a clean state for other tests


def test_secret_values_are_not_printed(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "dummy-key-for-test")
    get_settings.cache_clear()
    settings = get_settings()
    assert "dummy-key-for-test" not in repr(settings)
    assert settings.llm_api_key.get_secret_value() == "dummy-key-for-test"
    get_settings.cache_clear()