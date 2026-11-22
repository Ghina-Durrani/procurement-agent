"""Wait and try again when the provider says "too many requests" (HTTP 429).

Free tiers allow only a few requests and tokens per minute, so a long evaluation run hits the
limit often. Only rate limits are retried: a wrong key, a network failure or a server error
is reported at once, as before (the extractor then fails closed).
"""
import time
from collections.abc import Callable

from .llm import LLMClient, LLMRateLimited

DEFAULT_MAX_RETRIES = 5
DEFAULT_FIRST_WAIT_SECONDS = 5.0
MAX_WAIT_SECONDS = 120.0


class RetryingLLMClient:
    def __init__(
        self,
        inner: LLMClient,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        first_wait_seconds: float = DEFAULT_FIRST_WAIT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._inner = inner
        self._max_retries = max_retries
        self._first_wait = first_wait_seconds
        self._sleep = sleep  # tests pass a fake, so they never really wait
        self.waits: list[float] = []  # every wait, for run reports and tests

    def complete(self, system_prompt: str, user_message: str) -> str:
        for attempt in range(self._max_retries + 1):
            try:
                return self._inner.complete(system_prompt, user_message)
            except LLMRateLimited as error:
                if attempt == self._max_retries:
                    raise
                # Use the provider's own "retry after" when it gives one; otherwise double the wait.
                wait = error.retry_after_seconds or self._first_wait * (2**attempt)
                wait = min(max(wait, 0.0), MAX_WAIT_SECONDS)
                self.waits.append(wait)
                self._sleep(wait)
        raise AssertionError("unreachable")  # the loop always returns or raises
