"""A pretend LLM with scripted replies. Used by the tests and by the offline demo.

Nothing here calls the internet. Give it the replies you want, in order; an Exception in
the list is raised instead of returned, to imitate a provider failure.
"""
import json
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

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


def scripted_reply(
    values: Mapping[str, Any],
    evidence: Mapping[str, str | None] | None = None,
    *,
    statuses: Mapping[str, str] | None = None,
    urgency: tuple[str, str | None] | None = None,
    notes: Iterable[str] = (),
    **extra: Any,
) -> str:
    """Build a model reply in the extraction-v1 format from simple values.

    A field with a value is PRESENT unless statuses says otherwise; a field set to None is
    MISSING. Used by the tests and the offline demo, so scripted replies stay short.
    """
    evidence = evidence or {}
    statuses = statuses or {}
    reply: dict[str, Any] = {}
    for name in set(values) | set(statuses):
        value = values.get(name)
        status = statuses.get(name, "PRESENT" if value is not None else "MISSING")
        if isinstance(value, Decimal):
            value = str(value)
        reply[name] = {"status": status, "value": value, "evidence": evidence.get(name)}
    if urgency is not None:
        reply["urgency"] = {"level": urgency[0], "evidence": urgency[1]}
    reply["notes"] = list(notes)
    reply.update(extra)
    return json.dumps(reply)
