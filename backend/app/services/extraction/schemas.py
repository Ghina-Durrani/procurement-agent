"""Data shapes for the extraction agent.

Two shapes on purpose:
- LLMExtraction is what the model is asked to return. It is untrusted.
- ExtractionResult is what the rest of the system may use, after our code has checked it.
"""
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.policy import ExtractionStatus

# Words a model sometimes writes instead of a real null.
_NULL_WORDS = {"", "null", "none", "n/a", "na", "unknown", "not stated", "not specified"}

# The fields whose value must be backed by words copied from the request.
FIELDS_WITH_EVIDENCE = (
    "item_description",
    "quantity",
    "estimated_total",
    "currency",
    "supplier_name",
    "business_justification",
    "delivery_deadline",
)

# Every field the extraction can fill in (used to check the names in "required_fields").
EXTRACTED_FIELDS = (*FIELDS_WITH_EVIDENCE, "unit", "item_category", "urgency_evidence")


def _clean_text(value: Any) -> Any:
    if isinstance(value, str):
        value = " ".join(value.split())
        return None if value.casefold() in _NULL_WORDS else value
    return value


def _clean_number(value: Any) -> Any:
    if isinstance(value, bool):
        raise ValueError("a number is expected, not true/false")
    if isinstance(value, str):
        # "45,000" -> "45000". Nothing else is guessed.
        value = value.replace(",", "").strip()
        return None if value.casefold() in _NULL_WORDS else value
    return value


class LLMExtraction(BaseModel):
    """The JSON object the model returns. Unknown extra keys are dropped, never used."""

    model_config = ConfigDict(extra="ignore")

    item_description: str | None = Field(default=None, max_length=500)
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, max_length=50)
    estimated_total: Decimal | None = None
    currency: str | None = Field(default=None, max_length=10)
    item_category: str | None = Field(default=None, max_length=60)
    supplier_name: str | None = Field(default=None, max_length=200)
    delivery_deadline: str | None = Field(default=None, max_length=200)
    business_justification: str | None = Field(default=None, max_length=1000)
    urgency_evidence: str | None = Field(default=None, max_length=300)
    evidence: dict[str, str | None] = Field(default_factory=dict)
    ambiguities: list[str] = Field(default_factory=list, max_length=20)

    @field_validator(
        "item_description",
        "unit",
        "currency",
        "item_category",
        "supplier_name",
        "delivery_deadline",
        "business_justification",
        "urgency_evidence",
        mode="before",
    )
    @classmethod
    def _text(cls, value: Any) -> Any:
        return _clean_text(value)

    @field_validator("quantity", "estimated_total", mode="before")
    @classmethod
    def _number(cls, value: Any) -> Any:
        return _clean_number(value)

    @field_validator("quantity")
    @classmethod
    def _quantity_is_positive(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("quantity must be greater than zero")
        return value


class ExtractionResult(BaseModel):
    """The checked result. Safe to hand to the policy engine (see to_policy_input)."""

    model_config = ConfigDict(frozen=True)

    status: ExtractionStatus
    item_description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    estimated_total: Decimal | None = None
    currency: str | None = None
    item_category: str | None = None
    supplier_name: str | None = None
    delivery_deadline: str | None = None
    business_justification: str | None = None
    urgency_evidence: str | None = None
    # Required details that are still empty. Worked out by our code, not by the model.
    missing_fields: list[str] = Field(default_factory=list)
    # Notes for a human: unclear or conflicting information, and values we threw away.
    ambiguities: list[str] = Field(default_factory=list)
    # Why the status is INVALID or FAILED (never contains the request text).
    problems: list[str] = Field(default_factory=list)
    # Exact words from the request that back each kept value.
    evidence: dict[str, str] = Field(default_factory=dict)
