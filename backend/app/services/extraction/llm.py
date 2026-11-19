"""The LLM interface, and the errors any provider can raise.

The rest of the code only knows LLMClient. Which service sits behind it (Groq, OpenAI,
a fake for tests) is decided in one place, so switching provider never touches the logic.
"""
from typing import Protocol


class LLMError(Exception):
    """Base class. The message never contains the API key or the request text."""


class LLMNotConfigured(LLMError):
    """No API key (or a bad provider address) in the settings."""


class LLMAuthError(LLMError):
    """The provider refused our key (HTTP 401 or 403)."""


class LLMRateLimited(LLMError):
    """Too many requests or tokens (HTTP 429). Free tiers have small limits."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class LLMRequestFailed(LLMError):
    """Network problem, timeout, server error, or an answer we cannot read."""


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_message: str) -> str:
        """Send one prompt, return the model's text. Raise an LLMError on any failure."""
        ...
