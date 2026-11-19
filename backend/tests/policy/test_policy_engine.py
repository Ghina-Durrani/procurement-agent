"""Edge cases, fail-closed behaviour and design guarantees of the policy engine.

The main example cases are in test_policy_examples.py.
"""
import ast
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from policy_factories import (
    NOW,
    OTHER_USER_ID,
    REQUEST_ID,
    demo_config,
    pre_po_request,
    recent,
    starting_request,
)
from pydantic import ValidationError

from app.policy import Checkpoint, PolicyOutcome, evaluate, rules

CONTINUE = PolicyOutcome.CONTINUE
BLOCK = PolicyOutcome.BLOCK
REVIEW = PolicyOutcome.HUMAN_REVIEW


def run(**changes: object):
    return evaluate(starting_request(**changes), demo_config())


# --- Fail closed (POL-900) -------------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        {"currency": "USD"},
        {"currency": None},
        {"estimated_total": Decimal("0.00")},
        {"estimated_total": Decimal("-5.00")},
        {"extraction_status": "INVALID"},
        {"extraction_status": None},
        {"submitted_at": None},
    ],
    ids=["usd", "no-currency", "zero", "negative", "invalid-extraction", "no-status", "no-time"],
)
def test_bad_or_missing_input_goes_to_human_review(changes: dict[str, object]) -> None:
    result = run(**changes)
    assert result.outcome == REVIEW
    assert "POL-900" in result.triggered_rule_ids


def test_unaccepted_currency_reason_names_the_currency() -> None:
    result = run(currency="USD")
    assert any("USD" in rule.reason for rule in result.triggered_rules)


def test_missing_amount_fires_completeness_and_fail_closed() -> None:
    result = run(estimated_total=None, missing_fields=["estimated_total"])
    assert result.outcome == REVIEW
    assert result.triggered_rule_ids[0] == "POL-001"
    assert "POL-900" in result.triggered_rule_ids


def test_unreadable_input_is_human_review_not_an_exception() -> None:
    payload = {
        "request_id": str(REQUEST_ID),
        "organization_id": str(demo_config().organization_id),
        "checkpoint": "SOMETHING_ELSE",
    }
    result = evaluate(payload, demo_config())
    assert result.outcome == REVIEW
    assert result.checkpoint is None
    assert result.triggered_rule_ids == ["POL-900"]


def test_float_money_in_raw_input_is_refused() -> None:
    payload = starting_request().model_dump(mode="json")
    payload["estimated_total"] = 30000.0
    result = evaluate(payload, demo_config())
    assert result.outcome == REVIEW
    assert result.triggered_rule_ids == ["POL-900"]


def test_raw_valid_input_is_accepted() -> None:
    payload = starting_request().model_dump(mode="json")
    assert evaluate(payload, demo_config()).outcome == CONTINUE


def test_missing_settings_go_to_human_review() -> None:
    result = evaluate(starting_request(), None)
    assert result.outcome == REVIEW
    assert result.policy_version is None
    assert result.triggered_rule_ids == ["POL-900"]


def test_broken_settings_go_to_human_review() -> None:
    broken = demo_config().model_dump(mode="json")
    broken["approval_tiers"] = []
    result = evaluate(starting_request(), broken)
    assert result.outcome == REVIEW
    assert result.triggered_rule_ids == ["POL-900"]


def test_settings_of_another_organization_are_refused() -> None:
    other_org = demo_config(organization_id=UUID(int=999))
    result = evaluate(starting_request(), other_org)
    assert result.outcome == REVIEW
    assert result.triggered_rule_ids == ["POL-900"]


def test_a_crashing_rule_never_gives_continue(monkeypatch: pytest.MonkeyPatch) -> None:
    def crash(*_: object) -> list[object]:
        raise RuntimeError("boom")

    monkeypatch.setitem(rules.RULE_FUNCTIONS, "POL-006", crash)
    result = run()
    assert result.outcome == REVIEW
    assert result.triggered_rule_ids == ["POL-900"]
    # The internal error text must not leak into the reason shown to users.
    assert all("boom" not in rule.reason for rule in result.triggered_rules)


def test_a_crashing_rule_does_not_hide_a_block(monkeypatch: pytest.MonkeyPatch) -> None:
    def crash(*_: object) -> list[object]:
        raise RuntimeError("boom")

    monkeypatch.setitem(rules.RULE_FUNCTIONS, "POL-006", crash)
    result = run(supplier_status="BLOCKED")
    assert result.outcome == BLOCK
    assert result.triggered_rule_ids == ["POL-005", "POL-900"]


# --- Checkpoints -----------------------------------------------------------------------


def pre_po(**changes: object):
    return evaluate(pre_po_request(**changes), demo_config())


def test_pre_po_starting_request_continues() -> None:
    assert pre_po().outcome == CONTINUE


def test_pre_po_without_quotation_count_goes_to_human_review() -> None:
    result = pre_po(quotation_count=None)
    assert result.outcome == REVIEW
    assert result.triggered_rule_ids == ["POL-900"]


def test_pre_po_without_a_selected_quotation_goes_to_human_review() -> None:
    result = pre_po(selected_quotation_total=None)
    assert result.outcome == REVIEW
    assert set(result.triggered_rule_ids) == {"POL-900"}


@pytest.mark.parametrize("amount", ["0.00", "-1.00"])
def test_pre_po_zero_or_negative_quotation_goes_to_human_review(amount: str) -> None:
    result = pre_po(selected_quotation_total=Decimal(amount))
    assert result.outcome == REVIEW
    assert "POL-900" in result.triggered_rule_ids


def test_pre_po_without_a_supplier_goes_to_human_review() -> None:
    result = pre_po(supplier_name=None, supplier_status=None)
    assert result.outcome == REVIEW
    assert result.triggered_rule_ids == ["POL-900"]


def test_pre_po_blocked_supplier_is_blocked() -> None:
    result = pre_po(supplier_status="BLOCKED")
    assert result.outcome == BLOCK
    assert result.triggered_rule_ids == ["POL-005"]


@pytest.mark.parametrize(
    ("total", "quotes", "expected"),
    [
        ("100000.00", 1, CONTINUE),
        ("100000.01", 2, REVIEW),
        ("100000.01", 3, CONTINUE),
    ],
)
def test_quotation_band_boundaries(total: str, quotes: int, expected: PolicyOutcome) -> None:
    # The approval for this amount was already given at intake, so only POL-003 can fire.
    result = pre_po(
        selected_quotation_total=Decimal(total),
        approved_total=Decimal(total),
        quotation_count=quotes,
    )
    assert result.outcome == expected


def test_quotation_rule_uses_the_selected_quotation_not_the_estimate() -> None:
    result = pre_po(
        estimated_total=Decimal("30000.00"),
        selected_quotation_total=Decimal("150000.00"),
        approved_total=Decimal("150000.00"),
        quotation_count=1,
    )
    assert result.triggered_rule_ids == ["POL-003"]


# --- Price changes between intake and purchase order (POL-002 at PRE_PO, D-039) --------


@pytest.mark.parametrize(
    ("cleared", "selected", "quotes", "expected_rules", "expected_roles"),
    [
        ("40000.00", "45000.00", 1, [], []),
        ("40000.00", "50000.00", 1, [], []),
        ("40000.00", "50000.01", 1, ["POL-002"], ["MANAGER"]),
        ("40000.00", "90000.00", 1, ["POL-002"], ["MANAGER"]),
        ("60000.00", "450000.00", 3, [], []),
        ("60000.00", "500000.01", 3, ["POL-002"], ["SENIOR_MANAGER"]),
        ("600000.00", "550000.00", 3, [], []),
    ],
    ids=[
        "small-rise-same-tier",
        "rise-to-exact-limit",
        "rise-just-over-limit",
        "estimate-40k-quote-90k",
        "manager-approved-stays-manager",
        "manager-approved-needs-senior",
        "price-went-down",
    ],
)
def test_price_change_needs_a_more_senior_approver_only_when_the_tier_rises(
    cleared: str,
    selected: str,
    quotes: int,
    expected_rules: list[str],
    expected_roles: list[str],
) -> None:
    result = pre_po(
        approved_total=Decimal(cleared),
        selected_quotation_total=Decimal(selected),
        quotation_count=quotes,
    )
    assert result.triggered_rule_ids == expected_rules
    assert result.required_approver_roles == expected_roles


def test_price_rise_reason_shows_both_amounts() -> None:
    result = pre_po(
        approved_total=Decimal("40000.00"), selected_quotation_total=Decimal("90000.00")
    )
    reason = result.triggered_rules[0].reason
    assert "90,000.00" in reason and "40,000.00" in reason


def test_nothing_cleared_yet_means_any_approval_tier_fires() -> None:
    result = pre_po(approved_total=None, selected_quotation_total=Decimal("90000.00"))
    assert result.triggered_rule_ids == ["POL-002"]
    assert result.required_approver_roles == ["MANAGER"]


def test_cheap_selected_quote_is_fine_even_if_other_quotes_were_expensive() -> None:
    # Only the selected quotation is passed in; a rejected expensive quote cannot escalate.
    result = pre_po(
        approved_total=Decimal("40000.00"),
        selected_quotation_total=Decimal("38000.00"),
        quotation_count=3,
    )
    assert result.outcome == CONTINUE


def test_selected_quotation_is_ignored_at_intake() -> None:
    result = run(selected_quotation_total=Decimal("900000.00"))
    assert result.outcome == CONTINUE


# --- Budget recheck before purchase order (POL-007 at PRE_PO, D-040) ------------------


@pytest.mark.parametrize(
    ("budget", "expected", "expected_roles"),
    [
        ("INSUFFICIENT", BLOCK, []),
        ("NEEDS_FINANCE_APPROVAL", REVIEW, ["FINANCE_APPROVER"]),
        (None, REVIEW, ["FINANCE_APPROVER"]),
        ("AVAILABLE", CONTINUE, []),
    ],
)
def test_budget_is_rechecked_before_purchase_order(
    budget: str | None, expected: PolicyOutcome, expected_roles: list[str]
) -> None:
    result = pre_po(budget_status=budget)
    assert result.outcome == expected
    assert result.required_approver_roles == expected_roles
    if expected != CONTINUE:
        assert result.triggered_rule_ids == ["POL-007"]


def test_several_problems_before_purchase_order_are_all_reported() -> None:
    result = pre_po(
        approved_total=Decimal("40000.00"),
        selected_quotation_total=Decimal("150000.00"),
        quotation_count=1,
        budget_status="INSUFFICIENT",
    )
    assert result.outcome == BLOCK
    assert result.triggered_rule_ids == ["POL-002", "POL-003", "POL-007"]
    assert result.required_approver_roles == ["MANAGER", "PROCUREMENT_OFFICER"]


def test_float_quotation_amount_in_raw_input_is_refused() -> None:
    payload = pre_po_request().model_dump(mode="json")
    payload["selected_quotation_total"] = 30000.0
    result = evaluate(payload, demo_config())
    assert result.outcome == REVIEW
    assert result.triggered_rule_ids == ["POL-900"]


def test_approval_by_a_different_person_is_allowed() -> None:
    result = run(checkpoint=Checkpoint.APPROVAL, acting_user_id=OTHER_USER_ID)
    assert result.outcome == CONTINUE


def test_approval_without_knowing_who_approves_goes_to_human_review() -> None:
    result = run(checkpoint=Checkpoint.APPROVAL, acting_user_id=None)
    assert result.outcome == REVIEW
    assert result.triggered_rule_ids == ["POL-900"]


def test_intake_rules_do_not_run_at_approval() -> None:
    result = run(
        checkpoint=Checkpoint.APPROVAL,
        acting_user_id=OTHER_USER_ID,
        budget_status="INSUFFICIENT",
        item_category="WEAPONS",
    )
    assert result.outcome == CONTINUE


# --- Individual rule details ------------------------------------------------------------


def test_missing_detail_that_is_not_required_is_ignored() -> None:
    assert run(missing_fields=["needed_by_date"]).outcome == CONTINUE


def test_supplier_named_but_not_found_goes_to_review() -> None:
    result = run(supplier_name="Unknown Co", supplier_status=None)
    assert result.outcome == REVIEW
    assert result.triggered_rule_ids == ["POL-005"]


@pytest.mark.parametrize("category", ["GADGETS", None, ""])
def test_unknown_or_missing_category_is_never_treated_as_allowed(category: str | None) -> None:
    result = run(item_category=category)
    assert result.outcome == REVIEW
    assert result.triggered_rule_ids == ["POL-006"]
    assert result.required_approver_roles == ["PROCUREMENT_OFFICER"]


@pytest.mark.parametrize(
    ("category", "expected"),
    [(" software ", REVIEW), ("weapons", BLOCK), ("office_supplies", CONTINUE)],
)
def test_category_spelling_differences_are_normalised(
    category: str, expected: PolicyOutcome
) -> None:
    assert run(item_category=category).outcome == expected


def test_high_priority_is_not_an_emergency() -> None:
    assert run(proposed_priority="HIGH_PRIORITY").outcome == CONTINUE


def test_emergency_never_turns_a_block_into_review() -> None:
    result = run(proposed_priority="EMERGENCY", budget_status="INSUFFICIENT")
    assert result.outcome == BLOCK


def test_roles_are_listed_once() -> None:
    result = run(estimated_total=Decimal("1200000.00"), proposed_priority="EMERGENCY")
    assert result.required_approver_roles == ["SENIOR_MANAGER"]


# --- Split purchases (POL-004) ----------------------------------------------------------


def test_split_ignores_rejected_requests() -> None:
    earlier = recent(10, "35000.00", status="REJECTED")
    assert run(estimated_total=Decimal("40000.00"), recent_requests=[earlier]).outcome == CONTINUE


def test_split_ignores_other_suppliers() -> None:
    earlier = recent(10, "35000.00", supplier_name="Beta Supplies")
    assert run(estimated_total=Decimal("40000.00"), recent_requests=[earlier]).outcome == CONTINUE


def test_split_matches_supplier_names_loosely() -> None:
    earlier = recent(10, "35000.00", supplier_name="  alpha TRADERS ")
    result = run(estimated_total=Decimal("40000.00"), recent_requests=[earlier])
    assert result.triggered_rule_ids == ["POL-004"]


def test_split_uses_category_when_no_supplier_is_named() -> None:
    earlier = recent(10, "35000.00", supplier_name=None)
    result = run(
        estimated_total=Decimal("40000.00"),
        supplier_name=None,
        supplier_status=None,
        recent_requests=[earlier],
    )
    assert result.triggered_rule_ids == ["POL-004"]


def test_split_ignores_other_currencies() -> None:
    earlier = recent(10, "35000.00", currency="USD")
    assert run(estimated_total=Decimal("40000.00"), recent_requests=[earlier]).outcome == CONTINUE


def test_split_ignores_the_same_request() -> None:
    itself = recent(0, "35000.00", request_id=REQUEST_ID)
    assert run(estimated_total=Decimal("40000.00"), recent_requests=[itself]).outcome == CONTINUE


def test_split_window_includes_exactly_30_days() -> None:
    result = run(estimated_total=Decimal("40000.00"), recent_requests=[recent(30, "35000.00")])
    assert result.triggered_rule_ids == ["POL-004"]


def test_split_ignores_requests_dated_after_this_one() -> None:
    later = recent(0, "35000.00", submitted_at=NOW + timedelta(days=1))
    assert run(estimated_total=Decimal("40000.00"), recent_requests=[later]).outcome == CONTINUE


def test_split_reaching_a_limit_exactly_is_not_crossing_it() -> None:
    result = run(estimated_total=Decimal("25000.00"), recent_requests=[recent(5, "25000.00")])
    assert result.outcome == CONTINUE


def test_split_fires_when_this_request_is_exactly_at_the_limit() -> None:
    # 50,000.00 alone needs no approval, so adding more on top is still a split.
    result = run(estimated_total=Decimal("50000.00"), recent_requests=[recent(5, "1.00")])
    assert result.triggered_rule_ids == ["POL-004"]


def test_split_does_not_fire_when_this_request_is_already_over_the_limit() -> None:
    result = run(estimated_total=Decimal("60000.00"), recent_requests=[recent(5, "10000.00")])
    assert result.triggered_rule_ids == ["POL-002"]


def test_split_across_the_top_limit_adds_to_the_approval_rule() -> None:
    result = run(estimated_total=Decimal("450000.00"), recent_requests=[recent(5, "100000.00")])
    assert result.triggered_rule_ids == ["POL-002", "POL-004"]


# --- Design guarantees ------------------------------------------------------------------


def test_same_input_always_gives_the_same_result() -> None:
    data = starting_request(
        estimated_total=Decimal("40000.00"), recent_requests=[recent(5, "35000.00")]
    )
    assert evaluate(data, demo_config()) == evaluate(data, demo_config())


@pytest.mark.parametrize(
    "changes",
    [
        {
            "approval_tiers": [
                {"up_to": None, "approver_role": None},
                {"up_to": "10", "approver_role": None},
            ]
        },
        {
            "quotation_bands": [
                {"up_to": "500", "min_quotations": 1},
                {"up_to": "100", "min_quotations": 3},
            ]
        },
        {"allowed_categories": ["SOFTWARE"]},
    ],
    ids=["unbounded-tier-first", "bands-out-of-order", "category-in-two-lists"],
)
def test_inconsistent_settings_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        demo_config(**changes)


def test_policy_package_has_no_database_api_or_llm_imports() -> None:
    # BACKEND_GUIDE.md section 3: the policy package is pure and imports only these.
    allowed = {"app", "datetime", "decimal", "enum", "pydantic", "typing", "uuid", "collections"}
    package = Path(__file__).resolve().parents[2] / "app" / "policy"
    for source in package.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue  # relative import inside app.policy itself
                names = [node.module or ""]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                assert top in allowed, f"{source.name} imports {name}"
                if top == "app":
                    assert name.startswith("app.policy"), f"{source.name} imports {name}"
