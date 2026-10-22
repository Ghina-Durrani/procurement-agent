"""Application settings.

All configuration comes from environment variables (or the .env file in
development). Nothing secret is written in this file.
"""
from functools import lru_cache

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

    # Secret for the LLM provider.
    llm_api_key: SecretStr | None = None

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