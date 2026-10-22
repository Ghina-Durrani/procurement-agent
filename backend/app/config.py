"""Application settings.

All configuration comes from environment variables (or the .env file in
development). Nothing secret is written in this file.
"""
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # "development" or "production". Controls things like the /docs page.
    app_env: str = "development"

    # Secrets are optional for now; later tasks will require them.
    # SecretStr hides the value if the object is printed or logged by mistake.
    database_url: SecretStr | None = None
    llm_api_key: SecretStr | None = None

    # Limits that the SRS says must be configurable (placeholders for now).
    max_message_chars: int = 5000

    model_config = SettingsConfigDict(
        env_file="../.env",      # the .env file lives in the project root
        env_file_encoding="utf-8",
        extra="ignore",          # ignore variables that Docker uses (POSTGRES_*)
    )


@lru_cache
def get_settings() -> Settings:
    """Create the settings once and reuse them."""
    return Settings()