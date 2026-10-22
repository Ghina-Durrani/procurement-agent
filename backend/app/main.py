"""FastAPI entry point for Module 1 (Requirement Extraction)."""
from fastapi import FastAPI

from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    is_dev = settings.app_env == "development"

    app = FastAPI(
        title="Procurement Agent - Module 1",
        version="0.1.0",
        # Interactive API pages are shown only in development.
        docs_url="/docs" if is_dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if is_dev else None,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        # Says nothing about internals; only that the app is running.
        return {"status": "ok"}

    return app


app = create_app()