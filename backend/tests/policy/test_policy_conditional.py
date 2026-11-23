"""POL-001 with a detail that is required only in some cases: the business reason (D-053, D-054).

Demo settings: a reason is optional up to 50,000 PKR whatever the category, and required above
that and for a claimed emergency. A missing amount is asked for first; the reason rule is
checked again once the amount is known.
"""
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.policy import ConditionalRequirement, PolicyConfig, PolicyOutcome, evaluate
from tests.policy.policy_factories import demo_config, starting_request

NO_REASON = ["business_justification"]


def decide(config: PolicyConfig | None = None, **changes: Any):
    values = {"missing_fields": NO_REASON, **changes}
    return evaluate(starting_request(**values), config or demo_config())


def test_no_reason_is_fine_up_to_the_limit() -> None:
    assert decide().outcome is PolicyOutcome.CONTINUE  # 30,000 PKR office supplies
    assert decide(estimated_total=Decimal("50000.00")).outcome is PolicyOutcome.CONTINUE


@pytest.mark.parametrize("category", ["SOFTWARE", "VEHICLES", "HAZARDOUS_CHEMICALS"])
def test_the_category_alone_does_not_require_a_reason(category: str) -> None:
    result = decide(item_category=category, estimated_total=Decimal("20000.00"))
    assert "POL-001" not in result.triggered_rule_ids
    assert "POL-006" in result.triggered_rule_ids  # the category's own approval check stays


@pytest.mark.parametrize(
    ("changes", "why"),
    [
        ({"estimated_total": Decimal("50000.01")}, "above the limit"),
        ({"proposed_priority": "EMERGENCY"}, "emergency"),
        ({"item_category": "VEHICLES", "estimated_total": Decimal("4500000.00")}, "above the limit, any category"),
    ],
)
def test_a_reason_is_required_above_the_limit_and_for_an_emergency(changes: dict[str, Any], why: str) -> None:
    result = decide(**changes)
    pol_001 = next(rule for rule in result.triggered_rules if rule.rule_id == "POL-001")
    assert "business_justification" in pol_001.reason, why


def test_a_missing_amount_is_asked_for_first_not_the_reason() -> None:
    result = decide(estimated_total=None, missing_fields=["estimated_total", "business_justification"])
    pol_001 = next(rule for rule in result.triggered_rules if rule.rule_id == "POL-001")
    assert pol_001.reason == "Required detail still missing: estimated_total."
    assert result.outcome is PolicyOutcome.HUMAN_REVIEW  # never CONTINUE without an amount


def test_once_the_amount_is_known_the_reason_rule_applies_again() -> None:
    result = decide(estimated_total=Decimal("120000.00"))
    assert "POL-001" in result.triggered_rule_ids


def test_a_reason_can_still_be_required_by_category_when_configured() -> None:
    # Another organization may list categories explicitly; the setting still works.
    values = demo_config().model_dump()
    values["conditionally_required_fields"] = [
        {"field": "business_justification", "required_above": "50000.00", "required_for_categories": ["SOFTWARE"]}
    ]
    config = PolicyConfig.model_validate(values)
    result = decide(config, item_category="SOFTWARE", estimated_total=Decimal("20000.00"))
    assert "POL-001" in result.triggered_rule_ids


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
