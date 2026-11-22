"""Shared test data for the extraction tests. All requests and replies are made up."""
from typing import Any

from app.services.extraction import (
    FakeLLMClient,
    extract_request,
    known_categories,
    scripted_reply,
)
from app.services.extraction.schemas import EXTRACTED_FIELDS
from tests.policy.policy_factories import demo_config

TEXT = (
    "Please buy 10 office chairs from Alpha Traders. Total Rs 45,000. "
    "They are for the new HR room. Needed by 20 Nov."
)

GOOD: dict[str, Any] = {
    "item_description": "office chairs",
    "quantity": 10,
    "unit": "pieces",
    "estimated_total": 45000,
    "currency": "PKR",
    "item_category": "FURNITURE",
    "supplier_name": "Alpha Traders",
    "delivery_deadline": "20 Nov",
    "business_justification": "for the new HR room",
    "urgency_evidence": None,
    "evidence": {
        "item_description": "10 office chairs",
        # The category rests on the item words, as the prompt asks (a correct answer).
        "item_category": "10 office chairs",
        "quantity": "10 office chairs",
        "estimated_total": "Rs 45,000",
        "currency": "Rs 45,000",
        "supplier_name": "Alpha Traders",
        "delivery_deadline": "Needed by 20 Nov",
        "business_justification": "for the new HR room",
    },
    "ambiguities": [],
}


# Keys of the simple "flat" test style that are not field values.
_SPECIAL = {"evidence", "ambiguities", "urgency_evidence", "statuses"}


def as_reply(flat: dict[str, Any]) -> str:
    """Turn a simple flat dict (values + "evidence" + "ambiguities" ...) into a model reply in
    the extraction-v1 format: every field becomes {"status", "value", "evidence"}.

    Keys that are not known fields (for example "policy_outcome") are passed through as extra
    top-level keys, so tests can check that a fooled model's additions are ignored.
    """
    values = {k: v for k, v in flat.items() if k in EXTRACTED_FIELDS}
    extra = {k: v for k, v in flat.items() if k not in EXTRACTED_FIELDS and k not in _SPECIAL}
    urgency_words = flat.get("urgency_evidence")
    return scripted_reply(
        values,
        flat.get("evidence", {}),
        statuses=flat.get("statuses"),
        urgency=("URGENT", urgency_words) if urgency_words is not None else None,
        notes=flat.get("ambiguities", []),
        **extra,
    )


def reply(**changes: Any) -> str:
    """A model reply: the good example with some fields changed."""
    return as_reply({**GOOD, **changes})


def reply_without_evidence(*fields: str, **changes: Any) -> str:
    data = {**GOOD, **changes}
    data["evidence"] = {k: v for k, v in GOOD["evidence"].items() if k not in fields}
    return as_reply(data)


def run(replies: list[str | Exception], text: str = TEXT, **options: Any):
    """Run the extraction with scripted model replies. Returns (result, fake_llm)."""
    config = demo_config()
    llm = FakeLLMClient(replies)
    result = extract_request(
        text,
        llm,
        categories=known_categories(config),
        required_fields=config.required_fields,
        **options,
    )
    return result, llm
