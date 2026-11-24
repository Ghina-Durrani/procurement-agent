"""Which AI reads a submitted request in the app (D-059).

"fake" (default) spends no tokens. It answers only the 30 verified development cases, with
their checked labels, by reusing the experiment's LabelEchoLLM; for any other text it fails,
so the request fails closed (POL-900). The 50 held-out test cases are never loaded.
"live" uses the provider in .env through the existing factory. No retry wrapper: one
request should not hang for minutes on a rate limit, it should fail closed instead.
"""
from dataclasses import dataclass
from functools import lru_cache

from app.config import Settings, get_settings
from app.services.extraction import LLMClient, LLMError, build_llm_client

FAKE_MODEL_LABEL = "fake (development cases only)"


@dataclass(frozen=True)
class IntakeLLM:
    client: LLMClient
    label: str  # saved with each extraction, so a fake answer is never mistaken for a real one


class _Unavailable:
    """Stands in when the live client cannot be built (for example, no key): every call fails."""

    def __init__(self, error: LLMError) -> None:
        self._error = error

    def complete(self, system_prompt: str, user_message: str) -> str:
        raise self._error


@lru_cache
def _dev_case_client() -> LLMClient:
    # Imported here so the app only reads the evaluation files when fake mode is used.
    from app.services.evaluation.cases import Split, load_cases
    from app.services.evaluation.fake_models import LabelEchoLLM
    from app.services.evaluation.results import SystemName

    # Only the dev split, and only verified labels; the held-out test labels are never echoed.
    dev_cases = load_cases(require_verified=True, split=Split.DEV)
    return LabelEchoLLM(dev_cases, SystemName.B)


def build_intake_llm(settings: Settings | None = None) -> IntakeLLM:
    settings = settings or get_settings()
    if settings.extraction_mode == "fake":
        return IntakeLLM(_dev_case_client(), FAKE_MODEL_LABEL)
    try:
        return IntakeLLM(build_llm_client(settings), settings.llm_model)
    except LLMError as error:
        return IntakeLLM(_Unavailable(error), settings.llm_model)
