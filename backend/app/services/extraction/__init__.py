"""Extraction agent: turns an informal request into checked, structured details.

Typical use (the database and API layers will call this later):

    result = extract_request(text, build_llm_client(),
                             categories=known_categories(config),
                             required_fields=config.required_fields)
    policy_input = to_policy_input(result, request_id=..., organization_id=..., submitted_at=...)
    decision = evaluate(policy_input, config)
"""
from .convert import known_categories, to_policy_input
from .extractor import extract_request
from .factory import build_llm_client
from .fake_llm import FakeLLMClient
from .llm import (
    LLMAuthError,
    LLMClient,
    LLMError,
    LLMNotConfigured,
    LLMRateLimited,
    LLMRequestFailed,
)
from .schemas import ExtractionResult, LLMExtraction

__all__ = [
    "ExtractionResult",
    "FakeLLMClient",
    "LLMAuthError",
    "LLMClient",
    "LLMError",
    "LLMExtraction",
    "LLMNotConfigured",
    "LLMRateLimited",
    "LLMRequestFailed",
    "build_llm_client",
    "extract_request",
    "known_categories",
    "to_policy_input",
]
