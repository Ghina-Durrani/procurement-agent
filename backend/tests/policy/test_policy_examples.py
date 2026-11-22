"""The example cases from docs/POLICY_RULES.md section 7, one test each.

If a rule changes, the table in the document and this table must change together.
"""
from decimal import Decimal
from typing import Any

import pytest
from policy_factories import REQUESTER_ID, demo_config, recent, starting_request

from app.policy import Checkpoint, PolicyOutcome, evaluate

CONTINUE = PolicyOutcome.CONTINUE
BLOCK = PolicyOutcome.BLOCK
REVIEW = PolicyOutcome.HUMAN_REVIEW

# (case id, changes to the starting request, answer, rules fired, roles)
CASES: list[tuple[str, dict[str, Any], PolicyOutcome, list[str], list[str]]] = [
    ("C01", {}, CONTINUE, [], []),
    ("C02", {"missing_fields": ["quantity"]}, REVIEW, ["POL-001"], ["PROCUREMENT_OFFICER"]),
    ("C03", {"estimated_total": Decimal("50000.00")}, CONTINUE, [], []),
    ("C04", {"estimated_total": Decimal("50000.01")}, REVIEW, ["POL-002"], ["MANAGER"]),
    ("C05", {"estimated_total": Decimal("1200000.00")}, REVIEW, ["POL-002"], ["SENIOR_MANAGER"]),
    (
        "C06",
        {"estimated_total": Decimal("40000.00"), "recent_requests": [recent(20, "35000.00")]},
        REVIEW,
        ["POL-004"],
        ["PROCUREMENT_OFFICER"],
    ),
    (
        "C07",
        {"estimated_total": Decimal("40000.00"), "recent_requests": [recent(45, "35000.00")]},
        CONTINUE,
        [],
        [],
    ),
    ("C08", {"supplier_status": "BLOCKED"}, BLOCK, ["POL-005"], []),
    ("C09", {"supplier_status": "NOT_APPROVED"}, REVIEW, ["POL-005"], ["PROCUREMENT_OFFICER"]),
    ("C10", {"supplier_name": None, "supplier_status": None}, CONTINUE, [], []),
    ("C11", {"item_category": "WEAPONS"}, BLOCK, ["POL-006"], []),
    ("C12", {"item_category": "SOFTWARE"}, REVIEW, ["POL-006"], ["IT_APPROVER"]),
    ("C13", {"budget_status": "INSUFFICIENT"}, BLOCK, ["POL-007"], []),
    (
        "C14",
        {"budget_status": "NEEDS_FINANCE_APPROVAL"},
        REVIEW,
        ["POL-007"],
        ["FINANCE_APPROVER"],
    ),
    ("C15", {"budget_status": None}, REVIEW, ["POL-007"], ["FINANCE_APPROVER"]),
    ("C16", {"proposed_priority": "EMERGENCY"}, REVIEW, ["POL-008"], ["SENIOR_MANAGER"]),
    (
        "C17",
        {
            "estimated_total": Decimal("1200000.00"),
            "supplier_status": "BLOCKED",
            "proposed_priority": "EMERGENCY",
        },
        BLOCK,
        ["POL-002", "POL-005", "POL-008"],
        ["SENIOR_MANAGER"],
    ),
    (
        "C18",
        {
            "checkpoint": Checkpoint.PRE_PO,
            "selected_quotation_total": Decimal("300000.00"),
            "approved_total": Decimal("300000.00"),
            "quotation_count": 1,
        },
        REVIEW,
        ["POL-003"],
        ["PROCUREMENT_OFFICER"],
    ),
    ("C19", {"extraction_status": "FAILED"}, REVIEW, ["POL-900"], ["PROCUREMENT_OFFICER"]),
    (
        "C20",
        {"checkpoint": Checkpoint.APPROVAL, "acting_user_id": REQUESTER_ID},
        BLOCK,
        ["POL-009"],
        [],
    ),
    (
        "C21",
        {
            "checkpoint": Checkpoint.PRE_PO,
            "estimated_total": Decimal("40000.00"),
            "approved_total": Decimal("40000.00"),
            "selected_quotation_total": Decimal("90000.00"),
            "quotation_count": 1,
        },
        REVIEW,
        ["POL-002"],
        ["MANAGER"],
    ),
    (
        "C22",
        {
            "checkpoint": Checkpoint.PRE_PO,
            "estimated_total": Decimal("40000.00"),
            "approved_total": Decimal("40000.00"),
            "selected_quotation_total": Decimal("45000.00"),
            "quotation_count": 1,
        },
        CONTINUE,
        [],
        [],
    ),
    (
        "C23",
        {
            "checkpoint": Checkpoint.PRE_PO,
            "selected_quotation_total": Decimal("30000.00"),
            "approved_total": Decimal("30000.00"),
            "quotation_count": 1,
            "budget_status": "INSUFFICIENT",
        },
        BLOCK,
        ["POL-007"],
        [],
    ),
    (
        "C24",
        {"supplier_name": None, "supplier_status": None, "supplier_conflict": True},
        REVIEW,
        ["POL-005"],
        ["PROCUREMENT_OFFICER"],
    ),
    ("C25", {"instructions_in_request": True}, REVIEW, ["POL-010"], ["PROCUREMENT_OFFICER"]),
]


@pytest.mark.parametrize(
    ("changes", "expected_outcome", "expected_rules", "expected_roles"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_example_case(
    changes: dict[str, Any],
    expected_outcome: PolicyOutcome,
    expected_rules: list[str],
    expected_roles: list[str],
) -> None:
    result = evaluate(starting_request(**changes), demo_config())

    assert result.outcome == expected_outcome
    assert result.triggered_rule_ids == expected_rules
    assert result.required_approver_roles == expected_roles
    assert result.policy_version == "demo-2026-11-05.1"


def test_every_triggered_rule_has_a_reason() -> None:
    # A reviewer must always see why a rule fired.
    result = evaluate(
        starting_request(
            estimated_total=Decimal("1200000.00"),
            supplier_status="BLOCKED",
            proposed_priority="EMERGENCY",
        ),
        demo_config(),
    )
    assert all(rule.reason.strip() for rule in result.triggered_rules)
