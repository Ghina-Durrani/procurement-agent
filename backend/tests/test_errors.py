"""Every error uses the one envelope from ENGINEERING_HANDBOOK §3. No database needed."""
from fastapi.testclient import TestClient

from app.core.errors import NotFound
from app.main import create_app


def _client() -> TestClient:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("internal detail that must not leak")

    @app.get("/missing")
    def missing() -> None:
        raise NotFound("Request not found.")

    return TestClient(app, raise_server_exceptions=False)


def test_unknown_route_uses_the_envelope() -> None:
    response = _client().get("/no-such-route")
    assert response.status_code == 404
    assert response.json() == {"code": "NOT_FOUND", "message": "Not Found", "field_errors": None}


def test_wrong_method_uses_the_envelope() -> None:
    response = _client().delete("/health")
    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"


def test_domain_error_uses_its_code() -> None:
    response = _client().get("/missing")
    assert response.status_code == 404
    assert response.json() == {"code": "NOT_FOUND", "message": "Request not found.", "field_errors": None}


def test_unexpected_error_hides_internals() -> None:
    response = _client().get("/boom")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "internal detail" not in response.text
