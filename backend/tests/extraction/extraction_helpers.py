"""Shared test data for the extraction tests. All requests and replies are made up."""
import json
from typing import Any

from app.services.extraction import FakeLLMClient, extract_request, known_categories
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
        "quantity": "10 office chairs",
        "estimated_total": "Rs 45,000",
        "currency": "Rs 45,000",
        "supplier_name": "Alpha Traders",
        "delivery_deadline": "Needed by 20 Nov",
        "business_justification": "for the new HR room",
    },
    "ambiguities": [],
}


def reply(**changes: Any) -> str:
    """A model reply: the good example with some fields changed."""
    data = {**GOOD, **changes}
    return json.dumps(data)


def reply_without_evidence(*fields: str, **changes: Any) -> str:
    data = {**GOOD, **changes}
    data["evidence"] = {k: v for k, v in GOOD["evidence"].items() if k not in fields}
    return json.dumps(data)


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
