"""Safety findings 13 (CH-011) and 14 (CH-027): System B let two requests through.

Each test feeds System B the answer the real model gave in the saved challenge run
(20261123-192800-B-challenge), so the test reproduces the observed false allow. The checks
under test are general; case texts are only used as realistic examples. Local fake model only.
"""
import json
from typing import Any

from app.policy import PolicyOutcome, evaluate
from app.services.evaluation import load_context
from app.services.evaluation.cases import load_dataset
from app.services.evaluation.system_b import run_system_b
from app.services.extraction import (
    FakeLLMClient,
    extract_request,
    known_categories,
    scripted_reply,
    to_policy_input,
)

CONTEXT = load_context()
CHALLENGE = {case.case_id: case for case in load_dataset("challenge", for_scoring=False)}
CONTINUE, REVIEW, BLOCK = PolicyOutcome.CONTINUE, PolicyOutcome.HUMAN_REVIEW, PolicyOutcome.BLOCK


def _case(case_id: str, text: str | None = None):  # type: ignore[no-untyped-def]
    case = CHALLENGE[case_id]
    return case if text is None else case.model_copy(update={"request_text": text})


def _decide(case_id: str, reply: str, text: str | None = None):  # type: ignore[no-untyped-def]
    return run_system_b(_case(case_id, text), FakeLLMClient([reply]), CONTEXT)


def _reasons(text: str, reply: str) -> list[str]:
    """The engine's reasons for this reply, through the same steps System B uses."""
    config = CONTEXT.policy_config
    result = extract_request(
        text,
        FakeLLMClient([reply]),
        categories=known_categories(config),
        required_fields=config.fields_to_collect(),
    )
    from uuid import uuid4
    from datetime import UTC, datetime

    policy_input = to_policy_input(
        result,
        request_id=uuid4(),
        organization_id=config.organization_id,
        submitted_at=datetime(2026, 11, 5, 9, tzinfo=UTC),
        budget_status=CONTEXT.default_budget_status,
        blocked_suppliers_in_text=CONTEXT.suppliers.blocked_in(text),
    )
    return [rule.reason for rule in evaluate(policy_input, config).triggered_rules]


# --- Finding 13 / CH-011: stated total disagrees with quantity × unit price ----------------

WEBCAM_VALUES: dict[str, Any] = {
    "item_description": "webcams",
    "quantity": 10,
    "unit": "each",
    "estimated_total": "35000",
    "currency": "PKR",
    "item_category": "IT_HARDWARE",
    "business_justification": "for the remote team",
}
WEBCAM_EVIDENCE = {
    "item_description": "webcams",
    "quantity": "10 webcams",
    "unit": "each",
    "estimated_total": "total Rs 35,000",
    "currency": "Rs",
    "item_category": "webcams",
    "business_justification": "for the remote team",
}
UNIT_PRICE = {"status": "PRESENT", "value": "4000", "evidence": "Rs 4,000 each"}


def webcam_reply(total: str = "35000", total_quote: str = "total Rs 35,000", **extra: Any) -> str:
    values = {**WEBCAM_VALUES, "estimated_total": total}
    evidence = {**WEBCAM_EVIDENCE, "estimated_total": total_quote}
    return scripted_reply(values, evidence, **extra)


def test_ch011_mismatched_total_goes_to_review() -> None:
    result = _decide("CH-011", webcam_reply(unit_price=UNIT_PRICE))
    assert result.decision is REVIEW
    assert "POL-001" in result.triggered_rules


def test_ch011_review_reason_explains_the_mismatch() -> None:
    reasons = " ".join(_reasons(CHALLENGE["CH-011"].request_text, webcam_reply(unit_price=UNIT_PRICE)))
    assert "35,000" in reasons and "40,000" in reasons and "10 × 4,000" in reasons


def test_matching_total_passes_the_check() -> None:
    text = "Order 10 webcams at Rs 4,000 each for the remote team, total Rs 40,000."
    reply = webcam_reply("40000", "total Rs 40,000", unit_price=UNIT_PRICE)
    result = _decide("CH-011", reply, text)
    assert result.decision is CONTINUE
    assert result.triggered_rules == []


def test_small_rounding_difference_passes() -> None:
    text = "Order 3 webcams at Rs 3,333.33 each for the remote team, total Rs 10,000."
    values = {**WEBCAM_VALUES, "quantity": 3, "estimated_total": "10000"}
    evidence = {**WEBCAM_EVIDENCE, "quantity": "3 webcams", "estimated_total": "total Rs 10,000"}
    price = {"status": "PRESENT", "value": "3333.33", "evidence": "Rs 3,333.33 each"}
    result = _decide("CH-011", scripted_reply(values, evidence, unit_price=price), text)
    assert result.decision is CONTINUE


def test_unit_price_not_in_the_request_is_ignored() -> None:
    # A made-up unit price cannot create (or hide) a mismatch: its quote must be real text.
    text = "Order 10 webcams for the remote team, total Rs 35,000."
    fake_price = {"status": "PRESENT", "value": "4000", "evidence": "Rs 4,000 each"}
    result = _decide("CH-011", webcam_reply(unit_price=fake_price), text)
    assert result.decision is CONTINUE


# --- Finding 14 / CH-027: blocked supplier among open alternatives --------------------------

CHAIR_VALUES: dict[str, Any] = {
    "item_description": "office chairs",
    "quantity": 5,
    "estimated_total": "35000",
    "currency": "PKR",
    "item_category": "FURNITURE",
}
CHAIR_EVIDENCE = {
    "item_description": "office chairs",
    "quantity": "5 office chairs",
    "estimated_total": "Rs 35,000",
    "currency": "Rs",
    "item_category": "office chairs",
}


def chair_reply(supplier: dict[str, Any] | None) -> str:
    reply = json.loads(scripted_reply(CHAIR_VALUES, CHAIR_EVIDENCE))
    if supplier is not None:
        reply["supplier_name"] = supplier
    return json.dumps(reply)


def test_ch027_open_choice_with_a_blocked_candidate_goes_to_review() -> None:
    # Exactly what the model answered in the saved run: AMBIGUOUS, no value.
    ambiguous = {"status": "AMBIGUOUS", "value": None, "evidence": "Metro Furniture or QuickDeal Imports"}
    result = _decide("CH-027", chair_reply(ambiguous))
    assert result.decision is REVIEW
    assert result.triggered_rules == ["POL-005"]


def test_ch027_reason_names_the_blocked_supplier() -> None:
    ambiguous = {"status": "AMBIGUOUS", "value": None, "evidence": "Metro Furniture or QuickDeal Imports"}
    reasons = " ".join(_reasons(CHALLENGE["CH-027"].request_text, chair_reply(ambiguous)))
    assert "QuickDeal Imports" in reasons


def test_model_missing_the_supplier_still_catches_a_blocked_candidate() -> None:
    # Even if the model marks the supplier MISSING, the open choice is caught by code.
    result = _decide("CH-027", chair_reply(None))
    assert result.decision is REVIEW
    assert "POL-005" in result.triggered_rules


def test_explicitly_choosing_a_blocked_supplier_is_still_blocked() -> None:
    text = "Buy 5 office chairs, Rs 35,000, from QuickDeal Imports."
    chosen = {"status": "PRESENT", "value": "QuickDeal Imports", "evidence": "QuickDeal Imports"}
    result = _decide("CH-027", chair_reply(chosen), text)
    assert result.decision is BLOCK
    assert "POL-005" in result.triggered_rules


def test_open_choice_between_approved_suppliers_is_not_flagged() -> None:
    text = "Buy 5 office chairs, Rs 35,000, from Metro Furniture or Office Mart, whichever is cheaper."
    ambiguous = {"status": "AMBIGUOUS", "value": None, "evidence": "Metro Furniture or Office Mart"}
    result = _decide("CH-027", chair_reply(ambiguous), text)
    assert result.decision is CONTINUE


def test_clear_choice_of_an_approved_supplier_is_not_flagged() -> None:
    text = "Buy 5 office chairs, Rs 35,000, from Metro Furniture, not QuickDeal Imports."
    chosen = {"status": "PRESENT", "value": "Metro Furniture", "evidence": "Metro Furniture"}
    result = _decide("CH-027", chair_reply(chosen), text)
    assert result.decision is CONTINUE


# --- Challenge run 1 follow-ups (D-063): CH-005, CH-016, CH-032 ----------------------------

DESK_VALUES: dict[str, Any] = {
    "item_description": "desks",
    "quantity": 3,
    "estimated_total": "49500",
    "currency": "PKR",
    "item_category": "FURNITURE",
    "business_justification": "for the new finance cabin",
}
DESK_EVIDENCE = {
    "item_description": "desks",
    "quantity": "3 desks",
    "estimated_total": "forty-nine thousand five hundred rupees",
    "currency": "rupees",
    "item_category": "desks",
    "business_justification": "for the new finance cabin",
}


def test_ch005_amount_in_words_counts_as_evidence() -> None:
    # The saved run: the model gave 49500 with the words as evidence; the check discarded it.
    result = _decide("CH-005", scripted_reply(DESK_VALUES, DESK_EVIDENCE))
    assert result.fields["estimated_total"].status.value == "PRESENT"
    assert result.decision is CONTINUE


def test_amount_in_words_that_does_not_match_is_still_refused() -> None:
    reply = scripted_reply({**DESK_VALUES, "estimated_total": "45900"}, DESK_EVIDENCE)
    result = _decide("CH-005", reply)
    assert result.fields["estimated_total"].status.value != "PRESENT"
    assert result.decision is REVIEW


def test_ch016_correct_reading_of_a_supplier_correction_continues() -> None:
    text = CHALLENGE["CH-016"].request_text
    values = {**CHAIR_VALUES, "quantity": 4, "estimated_total": "28000", "supplier_name": "Office Mart"}
    evidence = {**CHAIR_EVIDENCE, "quantity": "4 office chairs", "estimated_total": "Rs 28,000",
                "supplier_name": "order them from Office Mart instead"}
    result = _decide("CH-016", scripted_reply(values, evidence), text)
    assert result.decision is CONTINUE


def test_shared_field_rules_cover_supplier_corrections_and_open_alternatives() -> None:
    from app.services.extraction.prompt import FIELD_RULES as raw

    FIELD_RULES = " ".join(raw.split())  # line breaks in the prompt do not matter
    assert "Actually, order from Office Mart instead" in FIELD_RULES  # correction → PRESENT
    assert "whichever is cheaper" in FIELD_RULES  # open alternatives → AMBIGUOUS
    assert "issue the invoice or receive the payment" in FIELD_RULES  # Q-010
    assert "delivery recipient" in FIELD_RULES


KEYBOARD_TEXT = "Order 3 keyboards from TechZone, Rs 9,000, for the new hires. The invoice should come from Rehman Computers."
KEYBOARD_VALUES: dict[str, Any] = {
    "item_description": "keyboards", "quantity": 3, "estimated_total": "9000", "currency": "PKR",
    "item_category": "IT_HARDWARE", "supplier_name": "TechZone", "business_justification": "for the new hires",
}
KEYBOARD_EVIDENCE = {
    "item_description": "keyboards", "quantity": "3 keyboards", "estimated_total": "Rs 9,000", "currency": "Rs",
    "item_category": "keyboards", "supplier_name": "TechZone", "business_justification": "for the new hires",
}
PAYEE = {"order_from": "TechZone", "invoice_or_payment": "Rehman Computers"}


def test_ch032_low_value_invoice_company_goes_to_review() -> None:
    # Under 50,000, so nothing else would send it to a person: only the supplier check can.
    result = _decide("CH-032", scripted_reply(KEYBOARD_VALUES, KEYBOARD_EVIDENCE, payment_party=PAYEE), KEYBOARD_TEXT)
    assert result.decision is REVIEW
    assert result.triggered_rules == ["POL-005"]


def test_ch032_reason_names_both_companies() -> None:
    reasons = " ".join(_reasons(KEYBOARD_TEXT, scripted_reply(KEYBOARD_VALUES, KEYBOARD_EVIDENCE, payment_party=PAYEE)))
    assert "TechZone" in reasons and "Rehman Computers" in reasons and "paid" in reasons
