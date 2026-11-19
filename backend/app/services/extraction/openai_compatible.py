"""A client for any service that offers an OpenAI-style "chat completions" API.

Groq, OpenAI and others use the same request format, so one small class covers them.
We use plain httpx (already installed), so there is no extra package to add.
"""
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr

from .llm import LLMAuthError, LLMNotConfigured, LLMRateLimited, LLMRequestFailed

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
# Reasoning models spend tokens thinking before they answer, so leave plenty of room.
_MAX_OUTPUT_TOKENS = 2000


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        parsed = urlparse(base_url)
        # The key travels in a header, so never send it over plain http to another machine.
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS):
            raise LLMNotConfigured("LLM_BASE_URL must start with https://")
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._transport = transport  # tests pass a fake network here

    def complete(self, system_prompt: str, user_message: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0,
            # Plain "JSON mode" is understood by all providers. Our own code checks the shape.
            "response_format": {"type": "json_object"},
            "max_completion_tokens": _MAX_OUTPUT_TOKENS,
        }
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(self._url, json=payload, headers=headers)
        except httpx.TimeoutException as error:
            raise LLMRequestFailed("The language model took too long to answer.") from error
        except httpx.HTTPError as error:
            raise LLMRequestFailed("The language model could not be reached.") from error

        status = response.status_code
        if status in (401, 403):
            raise LLMAuthError("The language model service rejected the API key.")
        if status == 429:
            raise LLMRateLimited("The language model rate limit was reached.", _retry_after(response))
        if status >= 400:
            # Only the status code is reported: the body could echo the request text.
            raise LLMRequestFailed(f"The language model service returned an error ({status}).")
        return _read_content(response)


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return float(response.headers["retry-after"])
    except (KeyError, ValueError):
        return None


def _read_content(response: httpx.Response) -> str:
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise LLMRequestFailed("The language model answer could not be read.") from error
    if not isinstance(content, str) or not content.strip():
        raise LLMRequestFailed("The language model returned an empty answer.")
    return content
