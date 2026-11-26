"""POL-001 and POL-005 with the two code-found inputs from findings 13 and 14 (D-062)."""
from app.policy import PolicyOutcome, SupplierStatus, evaluate
from app.services.extraction import names_in_text
from tests.policy.policy_factories import demo_config, pre_po_request, starting_request

REVIEW, BLOCK, CONTINUE = PolicyOutcome.HUMAN_REVIEW, PolicyOutcome.BLOCK, PolicyOutcome.CONTINUE


def _pol(result, rule_id: str):  # type: ignore[no-untyped-def]
    return [rule for rule in result.triggered_rules if rule.rule_id == rule_id]


def test_baseline_request_continues() -> None:
    assert evaluate(starting_request(), demo_config()).outcome is CONTINUE


def test_blocked_candidate_in_an_open_choice_needs_review() -> None:
    result = evaluate(starting_request(blocked_suppliers_named=["QuickDeal Imports"]), demo_config())
    assert result.outcome is REVIEW
    [rule] = _pol(result, "POL-005")
    assert "QuickDeal Imports" in rule.reason and rule.required_approver_role is not None


def test_explicit_blocked_choice_still_blocks_first() -> None:
    data = starting_request(
        supplier_name="QuickDeal Imports",
        supplier_status=SupplierStatus.BLOCKED,
        blocked_suppliers_named=["QuickDeal Imports"],
    )
    result = evaluate(data, demo_config())
    assert result.outcome is BLOCK
    assert [rule.outcome for rule in _pol(result, "POL-005")] == [BLOCK]


def test_blocked_candidate_also_needs_review_before_a_purchase_order() -> None:
    result = evaluate(pre_po_request(blocked_suppliers_named=["Falcon Wholesale"]), demo_config())
    assert _pol(result, "POL-005")[0].outcome is REVIEW


def test_conflicting_total_is_explained_in_pol_001() -> None:
    data = starting_request(
        estimated_total=None,
        missing_fields=["estimated_total"],
        field_conflicts={"estimated_total": "stated total 35,000 PKR does not match 10 × 4,000 = 40,000 PKR"},
    )
    [rule] = _pol(evaluate(data, demo_config()), "POL-001")
    assert rule.reason.startswith("Required detail is conflicting: estimated_total (stated total 35,000")


def test_missing_and_conflicting_details_are_both_named() -> None:
    data = starting_request(
        estimated_total=None,
        missing_fields=["quantity", "estimated_total"],
        field_conflicts={"estimated_total": "stated total x does not match y"},
    )
    [rule] = _pol(evaluate(data, demo_config()), "POL-001")
    assert "still missing: quantity." in rule.reason
    assert "conflicting: estimated_total (stated total x does not match y)" in rule.reason


def test_names_in_text_matches_whole_names_only() -> None:
    names = ["QuickDeal Imports", "Falcon Wholesale"]
    assert names_in_text("from metro or QUICKDEAL   imports", names) == ["QuickDeal Imports"]
    assert names_in_text("QuickDeal Importsters ltd", names) == []
    assert names_in_text("just QuickDeal please", names) == []
    assert names_in_text("Falcon Wholesale, or QuickDeal Imports.", names) == names
