"""Build the real LLM client from the settings (.env). One place decides the provider."""
from app.config import Settings, get_settings

from .llm import LLMClient, LLMNotConfigured
from .openai_compatible import OpenAICompatibleClient


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value().strip():
        raise LLMNotConfigured("LLM_API_KEY is not set in the .env file.")
    return OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
