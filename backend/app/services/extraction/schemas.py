"""Data shapes for the extraction agent (schema version extraction-v1).

Two shapes on purpose:
- LLMReply is what the model is asked to return. It is untrusted.
- ExtractionResult is what the rest of the system may use, after our code has checked it.

Every field has the same three parts (EXTRACTION_MODULE_DESIGN.md section 3):
- status: PRESENT, MISSING, AMBIGUOUS or CONFLICTING
- value: only when the status is PRESENT, otherwise None
- evidence: the exact words from the request, or None
"""
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.policy import ExtractionStatus

SCHEMA_VERSION = "extraction-v1"

# Words a model sometimes writes instead of a real null.
_NULL_WORDS = {"", "null", "none", "n/a", "na", "unknown", "not stated", "not specified"}


class FieldStatus(str, Enum):
    PRESENT = "PRESENT"  # the request clearly states it
    MISSING = "MISSING"  # the request does not say it
    AMBIGUOUS = "AMBIGUOUS"  # it says something unclear ("a few", "around 10")
    CONFLICTING = "CONFLICTING"  # two statements disagree ("5 laptops" ... "10 laptops")


class UrgencyLevel(str, Enum):
    """A SIGNAL reported from the text, never a decision or an approval (D-028)."""

    NORMAL = "NORMAL"  # no time pressure stated
    URGENT = "URGENT"  # time pressure stated ("ASAP", "needed tomorrow")
    EMERGENCY_CLAIMED = "EMERGENCY_CLAIMED"  # the requester claims an emergency; not verified


# The fields whose PRESENT value must be backed by words copied from the request.
FIELDS_WITH_EVIDENCE = (
    "item_description",
    "quantity",
    "estimated_total",
    "currency",
    "supplier_name",
    "business_justification",
    "delivery_deadline",
    "delivery_location",
)

# Every field the extraction reports, in display order. These names are also the names used
# in PolicyConfig.required_fields and in missing_fields (one naming convention, D-044).
EXTRACTED_FIELDS = (
    "item_description",
    "quantity",
    "unit",
    "estimated_total",
    "currency",
    "item_category",
    "supplier_name",
    "delivery_deadline",
    "delivery_location",
    "business_justification",
)

# Where each field is stored on procurement_requests (D-037). The two delivery fields are kept
# as the requester's raw words in extractions.extracted_data only; turning "by Friday" into a
# date is a later step (needed_by_date).
REQUEST_COLUMN_FOR_FIELD = {
    "item_description": "item_description",
    "quantity": "quantity",
    "unit": "unit",
    "estimated_total": "estimated_amount",
    "currency": "currency",
    "item_category": "category",
    "supplier_name": "supplier_name",
    "business_justification": "purpose",
}

_TEXT_LIMITS = {
    "item_description": 500,
    "unit": 50,
    "currency": 10,
    "item_category": 60,
    "supplier_name": 200,
    "delivery_deadline": 200,
    "delivery_location": 200,
    "business_justification": 1000,
}
_EVIDENCE_LIMIT = 500


def clean_text(value: Any) -> Any:
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


def _clean_status(value: Any) -> Any:
    # Models sometimes write "present" or "Present".
    return value.strip().upper() if isinstance(value, str) else value


class _LLMField(BaseModel):
    """One field as the model reports it. Unknown extra keys are dropped, never used."""

    model_config = ConfigDict(extra="ignore")

    status: FieldStatus = FieldStatus.MISSING
    evidence: str | None = Field(default=None, max_length=_EVIDENCE_LIMIT)

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, value: Any) -> Any:
        return _clean_status(value)

    @field_validator("evidence", mode="before")
    @classmethod
    def _evidence(cls, value: Any) -> Any:
        return clean_text(value)


class _TextField(_LLMField):
    value: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _value(cls, value: Any) -> Any:
        return clean_text(value)


class _QuantityField(_LLMField):
    # A whole number of items. 2.5 or "many" make the whole reply invalid (strict schema).
    value: int | None = Field(default=None, gt=0)

    @field_validator("value", mode="before")
    @classmethod
    def _value(cls, value: Any) -> Any:
        return _clean_number(value)


class _MoneyField(_LLMField):
    value: Decimal | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _value(cls, value: Any) -> Any:
        return _clean_number(value)


class _LLMUrgency(BaseModel):
    model_config = ConfigDict(extra="ignore")

    level: UrgencyLevel = UrgencyLevel.NORMAL
    evidence: str | None = Field(default=None, max_length=300)

    @field_validator("level", mode="before")
    @classmethod
    def _level(cls, value: Any) -> Any:
        return _clean_status(value)

    @field_validator("evidence", mode="before")
    @classmethod
    def _evidence(cls, value: Any) -> Any:
        return clean_text(value)


class _LLMInstructions(BaseModel):
    """Text in the request that tries to instruct the system, as the model reports it."""

    model_config = ConfigDict(extra="ignore")

    found: bool = False
    evidence: str | None = Field(default=None, max_length=300)


class LLMReply(BaseModel):
    """The JSON object the model returns. A field it leaves out counts as MISSING."""

    model_config = ConfigDict(extra="ignore")

    item_description: _TextField = Field(default_factory=_TextField)
    quantity: _QuantityField = Field(default_factory=_QuantityField)
    unit: _TextField = Field(default_factory=_TextField)
    estimated_total: _MoneyField = Field(default_factory=_MoneyField)
    currency: _TextField = Field(default_factory=_TextField)
    item_category: _TextField = Field(default_factory=_TextField)
    supplier_name: _TextField = Field(default_factory=_TextField)
    delivery_deadline: _TextField = Field(default_factory=_TextField)
    delivery_location: _TextField = Field(default_factory=_TextField)
    business_justification: _TextField = Field(default_factory=_TextField)
    urgency: _LLMUrgency = Field(default_factory=_LLMUrgency)
    instructions_to_system: _LLMInstructions = Field(default_factory=_LLMInstructions)
    notes: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _text_lengths(self) -> "LLMReply":
        # An over-long value is not a usable answer: the whole reply is rejected (strict).
        for name, limit in _TEXT_LIMITS.items():
            value = getattr(self, name).value
            if isinstance(value, str) and len(value) > limit:
                raise ValueError(f"{name} is longer than {limit} characters")
        return self


class ExtractedField(BaseModel):
    """One checked field. value is None unless status is PRESENT."""

    model_config = ConfigDict(frozen=True)

    status: FieldStatus = FieldStatus.MISSING
    value: int | Decimal | str | None = None
    evidence: str | None = None


class UrgencySignal(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: UrgencyLevel = UrgencyLevel.NORMAL
    evidence: str | None = None


def _all_missing() -> dict[str, ExtractedField]:
    return {name: ExtractedField() for name in EXTRACTED_FIELDS}


class ExtractionResult(BaseModel):
    """The checked result. Safe to hand to the policy engine (see to_policy_input)."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = SCHEMA_VERSION
    status: ExtractionStatus
    fields: dict[str, ExtractedField] = Field(default_factory=_all_missing)
    urgency: UrgencySignal = Field(default_factory=UrgencySignal)
    # Required details that are not PRESENT. Worked out by our code, not by the model.
    missing_fields: list[str] = Field(default_factory=list)
    # Notes for a human: unclear or conflicting information, and values we threw away.
    ambiguities: list[str] = Field(default_factory=list)
    # Why the status is INVALID or FAILED (never contains the request text).
    problems: list[str] = Field(default_factory=list)
    # Parts of the request that read like orders to the system, found by code (D-051).
    # The policy engine sends any such request to a person (POL-010).
    instructions_found: list[str] = Field(default_factory=list)

    def value(self, name: str) -> Any:
        """The field's value if it is PRESENT, otherwise None."""
        field = self.fields.get(name)
        return field.value if field is not None and field.status is FieldStatus.PRESENT else None

    def field_status(self, name: str) -> FieldStatus:
        field = self.fields.get(name)
        return field.status if field is not None else FieldStatus.MISSING

    # Short names, so callers can write result.quantity instead of result.value("quantity").
    @property
    def item_description(self) -> str | None:
        return self.value("item_description")

    @property
    def quantity(self) -> int | None:
        return self.value("quantity")

    @property
    def unit(self) -> str | None:
        return self.value("unit")

    @property
    def estimated_total(self) -> Decimal | None:
        return self.value("estimated_total")

    @property
    def currency(self) -> str | None:
        return self.value("currency")

    @property
    def item_category(self) -> str | None:
        return self.value("item_category")

    @property
    def supplier_name(self) -> str | None:
        return self.value("supplier_name")

    @property
    def delivery_deadline(self) -> str | None:
        return self.value("delivery_deadline")

    @property
    def delivery_location(self) -> str | None:
        return self.value("delivery_location")

    @property
    def business_justification(self) -> str | None:
        return self.value("business_justification")

    @property
    def urgency_evidence(self) -> str | None:
        return self.urgency.evidence

    @property
    def evidence(self) -> dict[str, str]:
        """Exact words backing each PRESENT value."""
        return {
            name: field.evidence
            for name, field in self.fields.items()
            if field.status is FieldStatus.PRESENT and field.evidence
        }
