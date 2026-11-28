"""FastAPI entry point for Module 1 (Requirement Extraction)."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.dev import router as dev_router
from app.api.v1.requests import router as requests_router
from app.api.v1.reviews import router as reviews_router
from app.config import get_settings
from app.core.errors import install_error_handlers


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

    # Only the listed browser origins may call the API (Q-003); no cookies are used yet.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        # X-Demo-User: development user switcher (D-065); refused outside development.
        allow_headers=["Content-Type", "X-Demo-User"],
    )
    install_error_handlers(app)
    app.include_router(requests_router, prefix="/api/v1")
    app.include_router(reviews_router, prefix="/api/v1")
    app.include_router(dev_router, prefix="/api/v1")
    return app


app = create_app()