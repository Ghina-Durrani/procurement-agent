"""A pretend model for dry runs: it answers each case with that case's own expected labels.

It checks the plumbing (prompts, parsing, the engine, result files, metrics) end to end without
the internet or an API key. Both systems then score perfectly by construction, so a dry run
is never a result: the run is marked fake_model=True and the metrics say so.
"""
import json
from typing import Any

from app.services.extraction import FieldStatus, LLMRequestFailed
from app.services.extraction.prompt import build_user_message

from .cases import EvaluationCase
from .results import SystemName


class LabelEchoLLM:
    def __init__(self, cases: list[EvaluationCase], system: SystemName) -> None:
        # The user message always ends with the wrapped request text, so it identifies the case.
        self._by_message = {build_user_message(case.request_text): case for case in cases}
        self._system = system
        self.calls = 0

    def complete(self, system_prompt: str, user_message: str) -> str:
        self.calls += 1
        case = next(
            (case for wrapped, case in self._by_message.items() if user_message.endswith(wrapped)),
            None,
        )
        if case is None:
            raise LLMRequestFailed("The fake model does not know this request.")
        return json.dumps(_reply_for_a(case) if self._system is SystemName.A else _reply_for_b(case))


def _fields(case: EvaluationCase) -> dict[str, dict[str, Any]]:
    # The whole request is a quote that really appears in it, so the evidence checks pass.
    return {
        name: {
            "status": field.status.value,
            "value": field.value,
            "evidence": None if field.status is FieldStatus.MISSING else case.request_text,
        }
        for name, field in case.expected_fields.items()
    }


def _urgency(case: EvaluationCase) -> dict[str, Any]:
    level = case.expected_urgency.value
    return {"level": level, "evidence": None if level == "NORMAL" else case.request_text}


def _reply_for_b(case: EvaluationCase) -> dict[str, Any]:
    return {**_fields(case), "urgency": _urgency(case), "notes": []}


def _reply_for_a(case: EvaluationCase) -> dict[str, Any]:
    return {
        "fields": _fields(case),
        "urgency": _urgency(case),
        "decision": case.expected_decision.value,
        "triggered_rules": case.expected_triggered_rules,
        "required_roles": case.expected_required_roles,
        "reason": "Dry run: expected labels echoed back.",
    }
