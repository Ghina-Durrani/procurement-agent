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
from .fake_llm import FakeLLMClient, scripted_reply
from .llm import (
    LLMAuthError,
    LLMClient,
    LLMError,
    LLMNotConfigured,
    LLMRateLimited,
    LLMRequestFailed,
)
from .schemas import (
    REQUEST_COLUMN_FOR_FIELD,
    SCHEMA_VERSION,
    ExtractedField,
    ExtractionResult,
    FieldStatus,
    LLMReply,
    UrgencyLevel,
    UrgencySignal,
)

__all__ = [
    "REQUEST_COLUMN_FOR_FIELD",
    "SCHEMA_VERSION",
    "ExtractedField",
    "ExtractionResult",
    "FakeLLMClient",
    "FieldStatus",
    "LLMAuthError",
    "LLMClient",
    "LLMError",
    "LLMReply",
    "LLMNotConfigured",
    "LLMRateLimited",
    "LLMRequestFailed",
    "build_llm_client",
    "extract_request",
    "known_categories",
    "scripted_reply",
    "to_policy_input",
    "UrgencyLevel",
    "UrgencySignal",
]
