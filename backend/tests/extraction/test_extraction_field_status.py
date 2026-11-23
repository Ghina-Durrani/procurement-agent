"""Tests for the per-field status (extraction-v1): PRESENT, MISSING, AMBIGUOUS, CONFLICTING.

The model proposes a status; our code only keeps PRESENT when the value is backed by words
that really appear in the request. All requests and replies are made up.
"""
from app.models import ProcurementRequest
from app.policy import ExtractionStatus, PolicyOutcome
from app.services.extraction import (
    REQUEST_COLUMN_FOR_FIELD,
    SCHEMA_VERSION,
    FieldStatus,
    UrgencyLevel,
)
from app.services.extraction.schemas import EXTRACTED_FIELDS
from tests.extraction.extraction_helpers import GOOD, TEXT, as_reply, reply, run
from tests.extraction.test_extraction_to_policy import decide
from tests.policy.policy_factories import demo_config

PRESENT = FieldStatus.PRESENT
MISSING = FieldStatus.MISSING
AMBIGUOUS = FieldStatus.AMBIGUOUS
CONFLICTING = FieldStatus.CONFLICTING


# ---------- every result has the same shape ----------


def test_every_field_is_reported_with_a_status_and_the_schema_version():
    result, _ = run([reply()])
    assert result.schema_version == SCHEMA_VERSION == "extraction-v1"
    assert set(result.fields) == set(EXTRACTED_FIELDS)
    assert result.field_status("quantity") is PRESENT
    assert result.fields["quantity"].evidence == "10 office chairs"


def test_a_field_the_model_leaves_out_is_missing():
    result, _ = run([reply()])
    assert result.field_status("delivery_location") is MISSING
    assert result.fields["delivery_location"].value is None


def test_when_nothing_could_be_read_every_field_is_missing():
    result, _ = run(["not json", "still not json"])
    assert result.status is ExtractionStatus.INVALID
    assert all(field.status is MISSING for field in result.fields.values())


def test_quantity_is_a_whole_number():
    result, _ = run([reply()])
    assert result.quantity == 10 and isinstance(result.quantity, int)


def test_lower_case_status_words_from_the_model_are_accepted():
    result, _ = run([reply(statuses={"quantity": "present"})])
    assert result.field_status("quantity") is PRESENT


# ---------- AMBIGUOUS and CONFLICTING ----------


def test_an_unclear_quantity_is_ambiguous_and_still_counts_as_missing():
    text = "Need around 10 or so office chairs, total Rs 45,000, for the new HR room."
    raw = reply(
        quantity=None,
        statuses={"quantity": "AMBIGUOUS"},
        evidence={**GOOD["evidence"], "quantity": "around 10 or so"},
    )
    result, _ = run([raw], text=text)
    field = result.fields["quantity"]
    assert field.status is AMBIGUOUS
    assert field.value is None
    assert field.evidence == "around 10 or so"  # kept: useful for the clarification question
    assert "quantity" in result.missing_fields


def test_two_different_amounts_are_conflicting_and_go_to_human_review():
    text = "Buy 10 office chairs for Rs 45,000 for the HR room. Actually the total is Rs 60,000."
    raw = reply(
        estimated_total=None,
        statuses={"estimated_total": "CONFLICTING"},
        evidence={**GOOD["evidence"], "estimated_total": "Rs 60,000"},
        ambiguities=["Two different totals: Rs 45,000 and Rs 60,000."],
    )
    result, _ = run([raw], text=text)
    assert result.field_status("estimated_total") is CONFLICTING
    assert result.estimated_total is None
    decision = decide(result)
    assert decision.outcome is PolicyOutcome.HUMAN_REVIEW
    assert "POL-001" in decision.triggered_rule_ids


def test_a_value_sent_with_a_non_present_status_is_dropped():
    raw = reply(statuses={"supplier_name": "AMBIGUOUS"})  # value "Alpha Traders" still sent
    result, _ = run([raw])
    assert result.field_status("supplier_name") is AMBIGUOUS
    assert result.supplier_name is None
    assert result.fields["supplier_name"].value is None  # not stored either


def test_an_invented_quote_for_an_unclear_detail_is_dropped_with_a_note():
    raw = reply(
        quantity=None,
        statuses={"quantity": "AMBIGUOUS"},
        evidence={**GOOD["evidence"], "quantity": "a handful of chairs"},
    )
    result, _ = run([raw])
    assert result.fields["quantity"].evidence is None
    assert any("quantity" in note for note in result.ambiguities)


# ---------- PRESENT must be proven ----------


def test_present_without_supporting_words_becomes_missing():
    data = {**GOOD, "evidence": {k: v for k, v in GOOD["evidence"].items() if k != "supplier_name"}}
    result, _ = run([as_reply(data)])
    assert result.field_status("supplier_name") is MISSING
    assert any("supplier_name" in note for note in result.ambiguities)


def test_present_with_an_invented_quote_becomes_missing():
    result, _ = run([reply(evidence={**GOOD["evidence"], "supplier_name": "Zeta Corp"})])
    assert result.field_status("supplier_name") is MISSING
    assert result.fields["supplier_name"].evidence is None


def test_present_with_a_real_quote_that_does_not_match_the_number_becomes_ambiguous():
    # "Rs 45,000" is really in the request, but the model says 450000.
    result, _ = run([reply(estimated_total=450000)])
    field = result.fields["estimated_total"]
    assert field.status is AMBIGUOUS
    assert field.value is None
    assert field.evidence == "Rs 45,000"
    assert "estimated_total" in result.missing_fields


def test_present_without_a_value_counts_as_missing():
    raw = reply(statuses={"unit": "PRESENT"}, unit=None)
    result, _ = run([raw])
    assert result.field_status("unit") is MISSING


def test_no_unproven_value_is_ever_stored_in_a_field():
    """Whatever the model says, a field that is not PRESENT never carries a value."""
    raw = reply(
        estimated_total=450000,  # real quote, wrong number -> AMBIGUOUS
        statuses={"supplier_name": "CONFLICTING", "unit": "AMBIGUOUS"},
        evidence={**GOOD["evidence"], "business_justification": "invented words"},
    )
    result, _ = run([raw])
    for name, field in result.fields.items():
        if field.status is not PRESENT:
            assert field.value is None, name


def test_an_unknown_category_code_becomes_missing():
    result, _ = run([reply(item_category="SPACESHIPS")])
    assert result.field_status("item_category") is MISSING
    assert result.item_category is None


def test_delivery_location_is_kept_only_with_real_words():
    text = TEXT + " Deliver to the Clifton office."
    good = reply(
        delivery_location="Clifton office",
        evidence={**GOOD["evidence"], "delivery_location": "Deliver to the Clifton office"},
    )
    result, _ = run([good], text=text)
    assert result.delivery_location == "Clifton office"
    invented = reply(
        delivery_location="Head office",
        evidence={**GOOD["evidence"], "delivery_location": "Deliver to head office"},
    )
    result, _ = run([invented], text=text)
    assert result.field_status("delivery_location") is MISSING


def test_evidence_lists_only_present_fields():
    raw = reply(quantity=None, statuses={"quantity": "AMBIGUOUS"})
    result, _ = run([raw])
    assert "quantity" not in result.evidence
    assert result.evidence["supplier_name"] == "Alpha Traders"


# ---------- urgency is only a signal ----------


def test_stated_urgency_is_reported_with_its_words():
    text = TEXT + " This is very urgent."
    result, _ = run([reply(urgency_evidence="very urgent")], text=text)
    assert result.urgency.level is UrgencyLevel.URGENT
    assert result.urgency_evidence == "very urgent"


def test_a_claimed_emergency_with_invented_words_is_not_reported():
    raw = as_reply(GOOD).replace('"notes"', '"urgency": {"level": "EMERGENCY_CLAIMED", '
                                 '"evidence": "server room is on fire"}, "notes"')
    result, _ = run([raw])
    assert result.urgency.level is UrgencyLevel.NORMAL
    assert result.urgency.evidence is None
    assert any("urgency" in note for note in result.ambiguities)


def test_urgency_without_any_words_is_reported_as_normal():
    raw = as_reply(GOOD).replace(
        '"notes"', '"urgency": {"level": "URGENT", "evidence": null}, "notes"'
    )
    result, _ = run([raw])
    assert result.urgency.level is UrgencyLevel.NORMAL


def test_no_urgency_means_normal():
    result, _ = run([reply()])
    assert result.urgency.level is UrgencyLevel.NORMAL


# ---------- one naming convention (D-044) ----------


def test_required_field_names_are_extraction_fields():
    assert set(demo_config().fields_to_collect()) <= set(EXTRACTED_FIELDS)


def test_every_stored_field_maps_to_a_real_request_column():
    columns = {column.name for column in ProcurementRequest.__table__.columns}
    assert set(REQUEST_COLUMN_FOR_FIELD) <= set(EXTRACTED_FIELDS)
    assert set(REQUEST_COLUMN_FOR_FIELD.values()) <= columns


def test_every_required_field_has_a_request_column():
    assert set(demo_config().fields_to_collect()) <= set(REQUEST_COLUMN_FOR_FIELD)
