"""A second, separate version of the INTAKE rules, used only to check labels.

Written directly from docs/POLICY_RULES.md, without importing the engine's rule code. A label
is machine-validated only when three answers agree: the hand-written draft label, this
reference version, and the real policy engine. If two of them disagree, either the label or
one of the two implementations is wrong, and a person must look.

It reads the policy settings (limits, category lists, roles) as plain data, like a person
reading the settings page. It never runs a model.
"""
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from app.services.extraction import FieldStatus, UrgencyLevel

from .cases import EvaluationCase
from .context import EvaluationContext, supplier_status_for

REVIEW, BLOCK, CONTINUE = "HUMAN_REVIEW", "BLOCK", "CONTINUE"


@dataclass
class ReferenceAnswer:
    decision: str
    rules: list[str]
    roles: list[str]
    reasons: list[str] = field(default_factory=list)


def _norm(text: str | None) -> str:
    return " ".join((text or "").split()).casefold()


def reference_decision(case: EvaluationCase, context: EvaluationContext) -> ReferenceAnswer:
    cfg = context.policy_config
    officer = cfg.procurement_officer_role
    hits: list[tuple[str, str, str | None, str]] = []  # (rule, outcome, role, reason)

    def present(name: str):
        f = case.expected_fields[name]
        return f.value if f.status is FieldStatus.PRESENT else None

    amount = Decimal(str(present("estimated_total"))) if present("estimated_total") is not None else None
    currency = present("currency")
    category = present("item_category")
    supplier = present("supplier_name")
    emergency = case.expected_urgency is UrgencyLevel.EMERGENCY_CLAIMED
    missing = set(case.expected_missing_fields)

    # Fail-closed checks on the input ("POL-900: Did something go wrong?").
    if not currency:
        hits.append(("POL-900", REVIEW, officer, "currency missing"))
    elif currency.upper() not in {c.upper() for c in cfg.accepted_currencies}:
        hits.append(("POL-900", REVIEW, officer, "currency not accepted"))
    if amount is None:
        hits.append(("POL-900", REVIEW, officer, "amount missing, limits cannot be checked"))

    # POL-001: always-required details; the reason only above the limit or for an emergency.
    required = set(cfg.required_fields)
    for item in cfg.conditionally_required_fields:
        if (
            (item.required_above is not None and amount is not None and amount > item.required_above)
            or (item.required_for_emergency and emergency)
            or (category is not None and category in item.required_for_categories)
        ):
            required.add(item.field)
    if missing & required:
        hits.append(("POL-001", REVIEW, officer, f"missing {sorted(missing & required)}"))

    # POL-002: the approval level for the amount.
    if amount is not None:
        for tier in cfg.approval_tiers:
            if tier.up_to is None or amount <= tier.up_to:
                if tier.approver_role:
                    hits.append(("POL-002", REVIEW, tier.approver_role, f"amount {amount}"))
                break

    # POL-004: this request plus related earlier ones (30 days, not rejected or withdrawn, same
    # supplier when both name one, otherwise same category) crosses a limit it alone stays under.
    if amount is not None:
        start = context.submitted_at - timedelta(days=cfg.split_window_days)
        ignored = {s.upper() for s in cfg.split_ignored_statuses}
        combined = amount
        for earlier in case.context.recent_requests:
            when = context.submitted_at - timedelta(days=earlier.days_ago)
            if when < start or earlier.status.upper() in ignored:
                continue
            if supplier and earlier.supplier_name:
                related = _norm(supplier) == _norm(earlier.supplier_name)
            else:
                related = bool(category) and category == earlier.item_category
            if related:
                combined += earlier.estimated_total
        if any(amount <= limit < combined for limit in cfg.split_watched_thresholds):
            hits.append(("POL-004", REVIEW, officer, f"combined {combined}"))

    # POL-005: blocked supplier blocks; conflicting suppliers or one not on the approved list
    # go to the Procurement Officer; no supplier named is fine at this point.
    if case.status_of("supplier_name") is FieldStatus.CONFLICTING:
        hits.append(("POL-005", REVIEW, officer, "conflicting suppliers"))
    elif supplier:
        status = supplier_status_for(supplier, context.suppliers)
        if status is not None and status.value == "BLOCKED":
            hits.append(("POL-005", BLOCK, None, "blocked supplier"))
        elif status is None or status.value != "APPROVED":
            hits.append(("POL-005", REVIEW, officer, "supplier not approved"))

    # POL-006: prohibited blocks; controlled needs its approver; unknown goes to a person.
    if category in cfg.prohibited_categories:
        hits.append(("POL-006", BLOCK, None, "prohibited category"))
    elif category in cfg.controlled_categories:
        hits.append(("POL-006", REVIEW, cfg.controlled_categories[category], "controlled category"))
    elif category not in cfg.allowed_categories:
        hits.append(("POL-006", REVIEW, officer, "category unknown"))

    # POL-007: budget from finance.
    budget = (case.context.budget_status or context.default_budget_status).value
    if budget == "INSUFFICIENT":
        hits.append(("POL-007", BLOCK, None, "insufficient budget"))
    elif budget != "AVAILABLE":
        hits.append(("POL-007", REVIEW, cfg.finance_approver_role, "budget needs finance"))

    # POL-008: a claimed emergency needs the emergency approver.
    if emergency:
        hits.append(("POL-008", REVIEW, cfg.emergency_approver_role, "emergency claimed"))

    # POL-010: instructions aimed at the system.
    if case.expected_instructions_to_system:
        hits.append(("POL-010", REVIEW, officer, "instructions to the system"))

    outcomes = {outcome for _, outcome, _, _ in hits}
    decision = BLOCK if BLOCK in outcomes else REVIEW if REVIEW in outcomes else CONTINUE
    return ReferenceAnswer(
        decision=decision,
        rules=sorted({rule for rule, _, _, _ in hits}),
        roles=sorted({role for _, _, role, _ in hits if role}),
        reasons=[f"{rule}: {why}" for rule, _, _, why in hits],
    )


def reference_problems(case: EvaluationCase, context: EvaluationContext) -> list[str]:
    """Differences between the hand-written label and the reference version."""
    answer = reference_decision(case, context)
    problems = []
    if answer.decision != case.expected_decision.value:
        problems.append(f"reference policy gives {answer.decision}, label says {case.expected_decision.value}")
    if answer.rules != case.expected_triggered_rules:
        problems.append(f"reference policy gives rules {answer.rules}, label says {case.expected_triggered_rules}")
    if answer.roles != case.expected_required_roles:
        problems.append(f"reference policy gives roles {answer.roles}, label says {case.expected_required_roles}")
    return [f"{case.case_id}: {problem}" for problem in problems]
