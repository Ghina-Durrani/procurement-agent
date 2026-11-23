"""The policy rules: one small function per rule. See docs/POLICY_RULES.md section 5.

Each rule reads a PolicyInput and the organization's PolicyConfig and returns the
TriggeredRule entries it produces (an empty list when it does not fire). A rule
that needs information which is missing raises MissingInput instead of guessing;
the engine turns that into POL-900.
"""
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import TypeVar

from .types import (
    BudgetStatus,
    Checkpoint,
    ExtractionStatus,
    PolicyConfig,
    PolicyInput,
    PolicyOutcome,
    Priority,
    RecentRequest,
    SupplierStatus,
    TriggeredRule,
)

BLOCK = PolicyOutcome.BLOCK
REVIEW = PolicyOutcome.HUMAN_REVIEW

FAIL_CLOSED_RULE_ID = "POL-900"

Rule = Callable[[PolicyInput, PolicyConfig], list[TriggeredRule]]
T = TypeVar("T")


class MissingInput(Exception):
    """A rule needs a value that was not provided."""

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


def _need(value: T | None, field: str) -> T:
    if value is None:
        raise MissingInput(field)
    return value


def _money(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def _code(value: str | None) -> str | None:
    # Category and currency codes from the LLM may differ in case or spacing.
    return value.strip().upper() if value is not None else None


def _name(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return " ".join(value.split()).casefold()


def fail_closed(role: str | None, reason: str) -> TriggeredRule:
    return TriggeredRule(
        rule_id=FAIL_CLOSED_RULE_ID, outcome=REVIEW, reason=reason, required_approver_role=role
    )


def input_checks(data: PolicyInput, config: PolicyConfig) -> list[TriggeredRule]:
    """POL-900 checks on the input itself, for the checkpoints that handle amounts."""
    if data.checkpoint not in (Checkpoint.INTAKE, Checkpoint.PRE_PO):
        return []
    role = config.procurement_officer_role
    found: list[TriggeredRule] = []
    extraction = data.extraction_status
    if data.checkpoint is Checkpoint.INTAKE and extraction is not ExtractionStatus.VALID:
        status = extraction.value if extraction else "missing"
        found.append(fail_closed(role, f"The request could not be read reliably ({status})."))
    currency = _code(data.currency)
    if not currency:
        found.append(fail_closed(role, "Currency is missing."))
    elif currency not in {_code(c) for c in config.accepted_currencies}:
        found.append(fail_closed(role, f"Currency '{data.currency}' is not accepted."))
    for amount in (data.estimated_total, data.selected_quotation_total, data.approved_total):
        if amount is not None and amount <= 0:
            found.append(fail_closed(role, "Amount must be greater than zero."))
            break
    return found


def _required_now(data: PolicyInput, config: PolicyConfig) -> list[str]:
    """Always-required details, plus the conditional ones whose condition holds (D-053)."""
    required = list(config.required_fields)
    for item in config.conditionally_required_fields:
        amount, category = data.estimated_total, data.item_category
        if (
            (item.required_above is not None and (amount is None or amount > item.required_above))
            or (item.required_for_emergency and data.proposed_priority is Priority.EMERGENCY)
            or (item.required_for_categories and (category is None or category in item.required_for_categories))
        ):
            required.append(item.field)
    return required


def completeness(data: PolicyInput, config: PolicyConfig) -> list[TriggeredRule]:
    """POL-001: required details still missing after the clarification loop."""
    missing = [field for field in _required_now(data, config) if field in data.missing_fields]
    if not missing:
        return []
    return [
        TriggeredRule(
            rule_id="POL-001",
            outcome=REVIEW,
            reason=f"Required detail still missing: {', '.join(missing)}.",
            required_approver_role=config.procurement_officer_role,
        )
    ]


def _tier_index(config: PolicyConfig, amount: Decimal) -> int:
    return next(
        index
        for index, tier in enumerate(config.approval_tiers)
        if tier.up_to is None or amount <= tier.up_to
    )


def approval_tiers(data: PolicyInput, config: PolicyConfig) -> list[TriggeredRule]:
    """POL-002: higher amounts need a more senior approver.

    INTAKE checks the requester's estimate. PRE_PO checks the selected quotation and fires
    only if it needs a more senior approver than the amount already cleared (D-039).
    """
    if data.checkpoint is Checkpoint.PRE_PO:
        final = _need(data.selected_quotation_total, "selected_quotation_total")
        index = _tier_index(config, final)
        cleared = -1 if data.approved_total is None else _tier_index(config, data.approved_total)
        role = config.approval_tiers[index].approver_role
        if index <= cleared or role is None:
            return []
        so_far = _money(data.approved_total) if data.approved_total is not None else "nothing"
        reason = (
            f"Selected quotation {_money(final)} {data.currency} needs {role} approval "
            f"(cleared so far: {so_far})."
        )
    else:
        total = _need(data.estimated_total, "estimated_total")
        role = config.approval_tiers[_tier_index(config, total)].approver_role
        if role is None:
            return []
        reason = f"Amount {_money(total)} {data.currency} needs {role} approval."
    return [
        TriggeredRule(
            rule_id="POL-002", outcome=REVIEW, reason=reason, required_approver_role=role
        )
    ]


def quotations(data: PolicyInput, config: PolicyConfig) -> list[TriggeredRule]:
    """POL-003: enough supplier quotations for the selected quotation's amount."""
    total = _need(data.selected_quotation_total, "selected_quotation_total")
    received = _need(data.quotation_count, "quotation_count")
    band = next(b for b in config.quotation_bands if b.up_to is None or total <= b.up_to)
    if received >= band.min_quotations:
        return []
    return [
        TriggeredRule(
            rule_id="POL-003",
            outcome=REVIEW,
            reason=f"{band.min_quotations} quotation(s) required, {received} received.",
            required_approver_role=config.procurement_officer_role,
        )
    ]


def _is_related(data: PolicyInput, earlier: RecentRequest) -> bool:
    supplier, earlier_supplier = _name(data.supplier_name), _name(earlier.supplier_name)
    if supplier and earlier_supplier:
        return supplier == earlier_supplier
    category = _code(data.item_category)
    return bool(category) and category == _code(earlier.item_category)


def split_purchase(data: PolicyInput, config: PolicyConfig) -> list[TriggeredRule]:
    """POL-004: this request plus related recent ones crosses a limit it alone stays under."""
    total = _need(data.estimated_total, "estimated_total")
    submitted = _need(data.submitted_at, "submitted_at")
    window_start = submitted - timedelta(days=config.split_window_days)
    ignored = {status.upper() for status in config.split_ignored_statuses}
    related = [
        earlier
        for earlier in data.recent_requests
        if earlier.request_id != data.request_id
        and window_start <= earlier.submitted_at <= submitted
        and _code(earlier.currency) == _code(data.currency)
        and earlier.status.upper() not in ignored
        and _is_related(data, earlier)
    ]
    combined = total + sum((earlier.estimated_total for earlier in related), Decimal(0))
    crossed = [limit for limit in config.split_watched_thresholds if total <= limit < combined]
    if not crossed:
        return []
    return [
        TriggeredRule(
            rule_id="POL-004",
            outcome=REVIEW,
            reason=(
                f"Possible split purchase: combined total {_money(combined)} {data.currency} "
                f"is over the {_money(max(crossed))} limit."
            ),
            required_approver_role=config.procurement_officer_role,
        )
    ]


def supplier_list(data: PolicyInput, config: PolicyConfig) -> list[TriggeredRule]:
    """POL-005: blocked, unapproved or conflicting suppliers."""
    name, status = data.supplier_name, data.supplier_status
    if status is SupplierStatus.BLOCKED:
        return [
            TriggeredRule(
                rule_id="POL-005",
                outcome=BLOCK,
                reason=f"Supplier '{name}' is on the blocked list.",
            )
        ]
    if data.supplier_conflict:
        # One of the named suppliers could be blocked, so "no supplier yet" would be unsafe.
        # Not BLOCK: the request itself may be fine; only the supplier choice is unclear (D-048).
        return [
            TriggeredRule(
                rule_id="POL-005",
                outcome=REVIEW,
                reason="The request names conflicting suppliers; confirm which one is meant.",
                required_approver_role=config.procurement_officer_role,
            )
        ]
    if status is SupplierStatus.NOT_APPROVED or (status is None and _name(name)):
        return [
            TriggeredRule(
                rule_id="POL-005",
                outcome=REVIEW,
                reason=f"Supplier '{name}' is not on the approved supplier list.",
                required_approver_role=config.procurement_officer_role,
            )
        ]
    if status is None and data.checkpoint is Checkpoint.PRE_PO:
        # A purchase order cannot be prepared without a chosen supplier.
        raise MissingInput("supplier_name")
    return []


def categories(data: PolicyInput, config: PolicyConfig) -> list[TriggeredRule]:
    """POL-006: prohibited categories, categories needing sign-off, and unknown ones."""
    category = _code(data.item_category)
    if category in {_code(c) for c in config.prohibited_categories}:
        return [
            TriggeredRule(
                rule_id="POL-006", outcome=BLOCK, reason=f"Category '{category}' is not allowed."
            )
        ]
    controlled = {_code(c): role for c, role in config.controlled_categories.items()}
    if category in controlled:
        role = controlled[category]
        return [
            TriggeredRule(
                rule_id="POL-006",
                outcome=REVIEW,
                reason=f"Category '{category}' needs {role} sign-off.",
                required_approver_role=role,
            )
        ]
    if category and category in {_code(c) for c in config.allowed_categories}:
        return []
    # The category comes from the LLM, so an unknown value is never treated as allowed.
    return [
        TriggeredRule(
            rule_id="POL-006",
            outcome=REVIEW,
            reason="Category could not be matched to the approved list.",
            required_approver_role=config.procurement_officer_role,
        )
    ]


def budget(data: PolicyInput, config: PolicyConfig) -> list[TriggeredRule]:
    """POL-007: budget availability (at PRE_PO, for the selected quotation; D-040).

    The finance check works out and reserves the budget outside this engine.
    """
    status = data.budget_status
    if status is BudgetStatus.AVAILABLE:
        return []
    if status is BudgetStatus.INSUFFICIENT:
        return [
            TriggeredRule(
                rule_id="POL-007", outcome=BLOCK, reason="Insufficient budget for this request."
            )
        ]
    reason = (
        "Budget needs finance approval."
        if status is BudgetStatus.NEEDS_FINANCE_APPROVAL
        else "Budget availability could not be confirmed."
    )
    return [
        TriggeredRule(
            rule_id="POL-007",
            outcome=REVIEW,
            reason=reason,
            required_approver_role=config.finance_approver_role,
        )
    ]


def emergency(data: PolicyInput, config: PolicyConfig) -> list[TriggeredRule]:
    """POL-008: emergencies need a named approver; urgency never loosens other rules."""
    if data.proposed_priority is not Priority.EMERGENCY:
        return []
    role = config.emergency_approver_role
    return [
        TriggeredRule(
            rule_id="POL-008",
            outcome=REVIEW,
            reason=f"Emergency request; {role} must confirm it is a genuine emergency.",
            required_approver_role=role,
        )
    ]


def instructions_to_system(data: PolicyInput, config: PolicyConfig) -> list[TriggeredRule]:
    """POL-010: the request tries to give orders to the system (D-051).

    Not BLOCK: the purchase itself may be allowed. But nothing read from a request that tries
    to steer the system can be trusted without a person looking at it.
    """
    if not data.instructions_in_request:
        return []
    return [
        TriggeredRule(
            rule_id="POL-010",
            outcome=REVIEW,
            reason="The request contains instructions aimed at the system; a person must check it.",
            required_approver_role=config.procurement_officer_role,
        )
    ]


def segregation_of_duties(data: PolicyInput, config: PolicyConfig) -> list[TriggeredRule]:
    """POL-009: the requester cannot approve their own request."""
    approver = _need(data.acting_user_id, "acting_user_id")
    requester = _need(data.requester_user_id, "requester_user_id")
    if approver != requester:
        return []
    return [
        TriggeredRule(
            rule_id="POL-009", outcome=BLOCK, reason="You cannot approve your own request."
        )
    ]


RULE_FUNCTIONS: dict[str, Rule] = {
    "POL-001": completeness,
    "POL-002": approval_tiers,
    "POL-003": quotations,
    "POL-004": split_purchase,
    "POL-005": supplier_list,
    "POL-006": categories,
    "POL-007": budget,
    "POL-008": emergency,
    "POL-009": segregation_of_duties,
    "POL-010": instructions_to_system,
}

# Which rules run at which moment (POLICY_RULES.md section 3).
RULES_BY_CHECKPOINT: dict[Checkpoint, tuple[str, ...]] = {
    Checkpoint.INTAKE: (
        "POL-001",
        "POL-002",
        "POL-004",
        "POL-005",
        "POL-006",
        "POL-007",
        "POL-008",
        "POL-010",
    ),
    Checkpoint.PRE_PO: ("POL-002", "POL-003", "POL-005", "POL-007"),
    Checkpoint.APPROVAL: ("POL-009",),
}
