"""Data shapes for the policy engine: what goes in, what comes out, and the settings.

These types know nothing about the database, the API or the LLM. Other modules
build a PolicyInput from their own data and pass it in. See docs/POLICY_RULES.md.
"""
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class PolicyOutcome(str, Enum):
    CONTINUE = "CONTINUE"
    BLOCK = "BLOCK"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class Checkpoint(str, Enum):
    """The moment in the workflow at which the engine is called."""

    INTAKE = "INTAKE"
    PRE_PO = "PRE_PO"
    APPROVAL = "APPROVAL"


class ExtractionStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    FAILED = "FAILED"


class SupplierStatus(str, Enum):
    APPROVED = "APPROVED"
    NOT_APPROVED = "NOT_APPROVED"
    BLOCKED = "BLOCKED"


class BudgetStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NEEDS_FINANCE_APPROVAL = "NEEDS_FINANCE_APPROVAL"
    INSUFFICIENT = "INSUFFICIENT"


class Priority(str, Enum):
    # Placeholder names until the schema is decided (Q-006, D-028).
    NORMAL = "NORMAL"
    HIGH_PRIORITY = "HIGH_PRIORITY"
    EMERGENCY = "EMERGENCY"


def _reject_float(value: Any) -> Any:
    # A float has already lost precision, so money must arrive as Decimal, int or string.
    if isinstance(value, float):
        raise ValueError("money must be a Decimal or a string, not a float")
    return value


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RecentRequest(_Frozen):
    """One earlier request by the same requester, used for split-purchase detection."""

    request_id: UUID
    submitted_at: AwareDatetime
    estimated_total: Decimal
    currency: str
    status: str
    supplier_name: str | None = None
    item_category: str | None = None

    reject_float_money = field_validator("estimated_total", mode="before")(_reject_float)


class PolicyInput(_Frozen):
    """Everything the rules may need. Fields a checkpoint does not use can stay empty."""

    request_id: UUID
    organization_id: UUID
    checkpoint: Checkpoint
    requester_user_id: UUID | None = None
    submitted_at: AwareDatetime | None = None
    extraction_status: ExtractionStatus | None = None
    missing_fields: list[str] = Field(default_factory=list)
    # The requester's estimate, as extracted from the request (used at INTAKE).
    estimated_total: Decimal | None = None
    # The chosen supplier quotation (used at PRE_PO). Unselected quotations are never passed in.
    selected_quotation_total: Decimal | None = None
    # The amount already cleared at INTAKE: the estimate if no approval was needed, or the amount
    # a human approver approved. Used at PRE_PO to detect a price rise that needs a more senior
    # approver. None means nothing has been cleared yet.
    approved_total: Decimal | None = None
    currency: str | None = None
    item_category: str | None = None
    supplier_name: str | None = None
    supplier_status: SupplierStatus | None = None
    # True when the request names suppliers that contradict each other, so no single supplier
    # could be read from it (D-048). POL-005 then asks a person to confirm which one is meant.
    supplier_conflict: bool = False
    budget_status: BudgetStatus | None = None
    proposed_priority: Priority | None = None
    quotation_count: int | None = Field(default=None, ge=0)
    acting_user_id: UUID | None = None
    recent_requests: list[RecentRequest] = Field(default_factory=list)

    reject_float_money = field_validator(
        "estimated_total", "selected_quotation_total", "approved_total", mode="before"
    )(_reject_float)


class ApprovalTier(_Frozen):
    # up_to=None means "no upper limit"; it must be the last tier.
    up_to: Decimal | None
    approver_role: str | None

    reject_float_money = field_validator("up_to", mode="before")(_reject_float)


class QuotationBand(_Frozen):
    up_to: Decimal | None
    min_quotations: int = Field(ge=0)

    reject_float_money = field_validator("up_to", mode="before")(_reject_float)


def _check_bands(bands: list[ApprovalTier] | list[QuotationBand], name: str) -> None:
    if not bands:
        raise ValueError(f"{name} must not be empty")
    limits = [band.up_to for band in bands]
    if limits[-1] is not None or any(limit is None for limit in limits[:-1]):
        raise ValueError(f"only the last entry of {name} may have no upper limit")
    bounded = [limit for limit in limits if limit is not None]
    if bounded != sorted(bounded) or len(set(bounded)) != len(bounded):
        raise ValueError(f"{name} limits must be in increasing order")


class PolicyConfig(_Frozen):
    """One organization's rule settings. Versioned so old decisions can be re-checked."""

    organization_id: UUID
    policy_version: str = Field(min_length=1)
    accepted_currencies: list[str] = Field(min_length=1)
    required_fields: list[str]
    approval_tiers: list[ApprovalTier]
    quotation_bands: list[QuotationBand]
    split_window_days: int = Field(gt=0)
    split_watched_thresholds: list[Decimal]
    split_ignored_statuses: list[str]
    allowed_categories: list[str]
    controlled_categories: dict[str, str]
    prohibited_categories: list[str]
    procurement_officer_role: str
    finance_approver_role: str
    emergency_approver_role: str

    @model_validator(mode="after")
    def check_consistency(self) -> "PolicyConfig":
        _check_bands(self.approval_tiers, "approval_tiers")
        _check_bands(self.quotation_bands, "quotation_bands")
        lists = [
            set(self.allowed_categories),
            set(self.controlled_categories),
            set(self.prohibited_categories),
        ]
        if (lists[0] & lists[1]) or (lists[0] & lists[2]) or (lists[1] & lists[2]):
            raise ValueError("a category may appear in only one category list")
        return self


class TriggeredRule(_Frozen):
    rule_id: str
    outcome: PolicyOutcome
    reason: str
    required_approver_role: str | None = None


class PolicyResult(_Frozen):
    outcome: PolicyOutcome
    # None only when the input was too broken to read its checkpoint.
    checkpoint: Checkpoint | None
    triggered_rules: list[TriggeredRule]
    required_approver_roles: list[str]
    # None only when no valid settings were available.
    policy_version: str | None

    @property
    def triggered_rule_ids(self) -> list[str]:
        return [rule.rule_id for rule in self.triggered_rules]
