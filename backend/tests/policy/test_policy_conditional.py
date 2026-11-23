"""POL-001 with a detail that is required only in some cases: the business reason (D-053).

Demo settings: a reason is optional for ordinary purchases up to 50,000 PKR, and required above
that, for a claimed emergency, and for SOFTWARE, HAZARDOUS_CHEMICALS and VEHICLES. Unknown
amount or category counts as "required" (fail closed).
"""
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.policy import ConditionalRequirement, PolicyConfig, PolicyOutcome, evaluate

from tests.policy.policy_factories import demo_config, starting_request

NO_REASON = ["business_justification"]


def decide(**changes: Any):
    return evaluate(starting_request(missing_fields=NO_REASON, **changes), demo_config())


def test_no_reason_is_fine_for_an_ordinary_purchase_up_to_the_limit() -> None:
    assert decide().outcome is PolicyOutcome.CONTINUE  # 30,000 PKR office supplies
    assert decide(estimated_total=Decimal("50000.00")).outcome is PolicyOutcome.CONTINUE


@pytest.mark.parametrize(
    ("changes", "why"),
    [
        ({"estimated_total": Decimal("50000.01")}, "above the limit"),
        ({"proposed_priority": "EMERGENCY"}, "emergency"),
        ({"item_category": "SOFTWARE"}, "listed category"),
        ({"item_category": "VEHICLES"}, "listed category"),
        ({"item_category": None}, "unknown category"),
    ],
)
def test_a_reason_is_required_in_the_listed_cases(changes: dict[str, Any], why: str) -> None:
    result = decide(**changes)
    assert "POL-001" in result.triggered_rule_ids, why
    pol_001 = next(rule for rule in result.triggered_rules if rule.rule_id == "POL-001")
    assert "business_justification" in pol_001.reason


def test_an_unknown_amount_makes_the_reason_required() -> None:
    data = starting_request(estimated_total=None, missing_fields=["estimated_total", "business_justification"])
    result = evaluate(data, demo_config())
    pol_001 = next(rule for rule in result.triggered_rules if rule.rule_id == "POL-001")
    assert pol_001.reason == "Required detail still missing: estimated_total, business_justification."


def test_always_required_details_are_unchanged() -> None:
    result = evaluate(starting_request(missing_fields=["quantity"]), demo_config())
    assert result.triggered_rule_ids == ["POL-001"]


def test_settings_without_conditions_keep_the_reason_always_required() -> None:
    # An organization that lists the reason as always required gets the old behaviour.
    config = demo_config().model_copy(
        update={"required_fields": ["quantity", "business_justification"], "conditionally_required_fields": []}
    )
    assert "POL-001" in evaluate(starting_request(missing_fields=NO_REASON), config).triggered_rule_ids


def test_fields_to_collect_lists_always_then_sometimes_required() -> None:
    assert demo_config().fields_to_collect() == [
        "item_description", "quantity", "estimated_total", "currency", "business_justification",
    ]


def _config_with(requirement: dict[str, Any], **changes: Any) -> PolicyConfig:
    values = demo_config().model_dump()
    values.update(conditionally_required_fields=[requirement], **changes)
    return PolicyConfig.model_validate(values)


def test_a_requirement_needs_at_least_one_condition() -> None:
    with pytest.raises(ValidationError, match="has no condition"):
        ConditionalRequirement(field="business_justification")


def test_a_detail_cannot_be_both_always_and_sometimes_required() -> None:
    with pytest.raises(ValidationError, match="already always required"):
        _config_with({"field": "quantity", "required_for_emergency": True})


def test_unknown_categories_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown categories"):
        _config_with({"field": "business_justification", "required_for_categories": ["GADGETS"]})


def test_the_limit_cannot_be_a_float() -> None:
    with pytest.raises(ValidationError, match="float"):
        ConditionalRequirement(field="business_justification", required_above=50000.0)
