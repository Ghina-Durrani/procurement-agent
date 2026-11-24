"""Application settings.

All configuration comes from environment variables (or the .env file in
development). Nothing secret is written in this file.
"""
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL
from pathlib import Path


class Settings(BaseSettings):
    # "development" or "production". Controls things like the /docs page.
    app_env: str = "development"

    # Database connection settings.
    postgres_user: str = "procurement_user"
    postgres_password: SecretStr | None = None
    postgres_db: str = "procurement_db"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5433

    # LLM provider. Any service with an OpenAI-style "chat completions" API works
    # (Groq, OpenAI, Gemini's OpenAI mode ...): change these three values, not the code.
    llm_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-120b"
    llm_timeout_seconds: float = 30.0

    # Development-only stand-in for login (D-058): the email of the seeded demo user that
    # every API call acts as. Ignored outside development, where calls are refused.
    demo_user_email: str | None = None

    # Which AI reads submitted requests in the app (D-059). "fake" (default) costs no tokens:
    # it answers only the 30 verified dev cases and fails closed on any other text.
    # "live" calls the provider above. The experiment commands are not affected.
    extraction_mode: Literal["fake", "live"] = "fake"

    # Browser origins allowed to call the API (Q-003). JSON list in .env.
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Limits that the SRS says must be configurable (placeholders for now).
    max_message_chars: int = 5000

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",          # ignore variables that Docker uses (POSTGRES_*)
    )

    def build_database_url(self) -> URL:

        """Build the PostgreSQL connection URL safely."""
        if self.postgres_password is None:
            raise RuntimeError("POSTGRES_PASSWORD is not set")

        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    """Create the settings once and reuse them."""
    return Settings()