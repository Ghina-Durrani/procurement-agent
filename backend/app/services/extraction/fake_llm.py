"""A pretend LLM with scripted replies. Used by the tests and by the offline demo.

Nothing here calls the internet. Give it the replies you want, in order; an Exception in
the list is raised instead of returned, to imitate a provider failure.
"""
from collections.abc import Iterable

from .llm import LLMRequestFailed


class FakeLLMClient:
    def __init__(self, replies: Iterable[str | Exception]) -> None:
        self._replies = list(replies)
        # Every (system_prompt, user_message) pair received, so tests can inspect them.
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_message: str) -> str:
        self.calls.append((system_prompt, user_message))
        if not self._replies:
            raise LLMRequestFailed("The fake model has no more scripted replies.")
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
