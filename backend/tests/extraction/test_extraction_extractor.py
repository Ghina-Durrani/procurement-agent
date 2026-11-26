"""Tests for extract_request: normal cases, bad model output, failures and fabricated values."""
from decimal import Decimal

import pytest

from app.policy import ExtractionStatus
from app.services.extraction import LLMAuthError, LLMRateLimited, LLMRequestFailed
from tests.extraction.extraction_helpers import (
    GOOD,
    TEXT,
    as_reply,
    reply,
    reply_without_evidence,
    run,
)

VALID = ExtractionStatus.VALID
INVALID = ExtractionStatus.INVALID
FAILED = ExtractionStatus.FAILED


# ---------- normal case ----------


def test_clean_request_gives_a_valid_complete_result():
    result, llm = run([reply()])
    assert result.status is VALID
    assert result.item_description == "office chairs"
    assert result.quantity == Decimal(10)
    assert result.estimated_total == Decimal(45000)
    assert result.currency == "PKR"
    assert result.item_category == "FURNITURE"
    assert result.supplier_name == "Alpha Traders"
    assert result.missing_fields == []
    assert result.problems == []
    assert len(llm.calls) == 1


def test_money_keeps_exact_decimal_places():
    # The model writes 1500.50 as a JSON number. A float would not be exact.
    text = "Need 10 office chairs, total PKR 1,500.50."
    evidence = {"quantity": "10 office chairs", "estimated_total": "PKR 1,500.50"}
    # Written by hand so the number stays exactly "1500.50" in the JSON text.
    raw = (
        '{"quantity": {"status": "PRESENT", "value": 10, "evidence": "%s"}, '
        '"estimated_total": {"status": "PRESENT", "value": 1500.50, "evidence": "%s"}}'
        % (evidence["quantity"], evidence["estimated_total"])
    )
    result, _ = run([raw], text=text)
    assert result.status is VALID
    assert result.estimated_total == Decimal("1500.50")
    assert str(result.estimated_total) == "1500.50"


def test_currency_and_category_are_normalised():
    result, _ = run([reply(currency="pkr", item_category="furniture")])
    assert result.currency == "PKR"
    assert result.item_category == "FURNITURE"


def test_reply_inside_a_code_fence_is_accepted():
    result, _ = run(["```json\n" + reply() + "\n```"])
    assert result.status is VALID


def test_unknown_extra_keys_from_the_model_are_ignored():
    # A fooled model might add a decision. It must never reach the result.
    raw = reply(policy_outcome="CONTINUE", approved=True)
    result, _ = run([raw])
    assert result.status is VALID
    assert "policy_outcome" not in result.model_dump()
    assert "approved" not in result.model_dump()


# ---------- missing information ----------


def test_missing_required_details_are_listed_by_our_code():
    raw = reply(
        quantity=None,
        estimated_total=None,
        currency=None,
        business_justification=None,
    )
    result, _ = run([raw])
    assert result.status is VALID
    assert result.missing_fields == ["quantity", "estimated_total", "currency", "business_justification"]


@pytest.mark.parametrize("word", ["null", "N/A", "unknown", "none", ""])
def test_null_like_words_count_as_missing(word):
    result, _ = run([reply(business_justification=word)])
    assert "business_justification" in result.missing_fields


def test_a_required_name_we_cannot_fill_counts_as_missing():
    from app.services.extraction import FakeLLMClient, extract_request

    result = extract_request(
        TEXT,
        FakeLLMClient([reply()]),
        categories=["FURNITURE"],
        required_fields=["item_description", "purchase_order_number"],
    )
    assert result.missing_fields == ["purchase_order_number"]


# ---------- values the request does not support (never invent) ----------


def test_value_without_supporting_words_is_discarded():
    result, _ = run([reply_without_evidence("estimated_total")])
    assert result.estimated_total is None
    assert "estimated_total" in result.missing_fields
    assert any("estimated_total" in note for note in result.ambiguities)


def test_quote_that_is_not_in_the_request_is_discarded():
    evidence = {**GOOD["evidence"], "supplier_name": "Zeta Corp"}
    result, _ = run([reply(evidence=evidence)])
    assert result.supplier_name is None
    assert any("supplier_name" in note for note in result.ambiguities)


def test_amount_that_does_not_match_its_quote_is_discarded():
    # The model read "Rs 45,000" but reported 450000.
    result, _ = run([reply(estimated_total=450000)])
    assert result.estimated_total is None
    assert "estimated_total" in result.missing_fields


def test_made_up_amount_with_a_made_up_quote_is_discarded():
    evidence = {**GOOD["evidence"], "estimated_total": "total is 100"}
    result, _ = run([reply(estimated_total=100, evidence=evidence)])
    assert result.estimated_total is None


@pytest.mark.parametrize(
    "text, quote, value",
    [
        ("Need 4 monitors, budget is 45k in total.", "45k", 45000),
        ("Need 4 monitors, budget is 1.5 lakh in total.", "1.5 lakh", 150000),
        ("Need 4 monitors, budget is 2 crore in total.", "2 crore", 20000000),
        ("Need 4 monitors, budget is 3,200,000 in total.", "3,200,000", 3200000),
    ],
)
def test_common_ways_of_writing_money_are_accepted(text, quote, value):
    evidence = {"estimated_total": quote, "quantity": "4 monitors", "item_description": "4 monitors"}
    raw = as_reply({"estimated_total": value, "quantity": 4, "item_description": "monitors",
                    "evidence": evidence})
    result, _ = run([raw], text=text)
    assert result.estimated_total == Decimal(value)


def test_amount_written_only_in_words_is_accepted_when_the_words_say_the_same_number():
    # D-063: number words are read like digits (it used to be discarded).
    text = "Need 4 monitors, budget is fifty thousand rupees."
    evidence = {"estimated_total": "fifty thousand rupees"}
    raw = as_reply({"estimated_total": 50000, "evidence": evidence})
    result, _ = run([raw], text=text)
    assert result.estimated_total == Decimal(50000)


def test_amount_in_words_that_cannot_be_read_is_still_discarded():
    text = "Need 4 monitors, budget is fifty grand."
    evidence = {"estimated_total": "fifty grand"}
    raw = as_reply({"estimated_total": 50000, "evidence": evidence})
    result, _ = run([raw], text=text)
    assert result.estimated_total is None


def test_quantity_in_words_is_accepted_on_the_quote_alone():
    text = "Please order two laptops for Rs 200,000."
    evidence = {"quantity": "two laptops", "estimated_total": "Rs 200,000"}
    raw = as_reply({"quantity": 2, "estimated_total": 200000, "evidence": evidence})
    result, _ = run([raw], text=text)
    assert result.quantity == Decimal(2)


def test_quote_matching_ignores_case_and_spacing_only():
    evidence = {**GOOD["evidence"], "supplier_name": "alpha   TRADERS"}
    result, _ = run([reply(evidence=evidence)])
    assert result.supplier_name == "Alpha Traders"


def test_unknown_category_is_dropped_with_a_note():
    result, _ = run([reply(item_category="SPACESHIPS")])
    assert result.item_category is None
    assert any("item_category" in note for note in result.ambiguities)


def test_urgency_words_that_are_not_in_the_request_are_dropped():
    result, _ = run([reply(urgency_evidence="extremely urgent emergency")])
    assert result.urgency_evidence is None


def test_urgency_words_that_are_in_the_request_are_kept():
    text = TEXT + " This is very urgent."
    result, _ = run([reply(urgency_evidence="very urgent")], text=text)
    assert result.urgency_evidence == "very urgent"


def test_model_notes_are_kept_and_capped():
    notes = [f"note {i}" for i in range(15)]
    result, _ = run([reply(ambiguities=notes)])
    assert 0 < len(result.ambiguities) <= 20


# ---------- bad model output ----------


def test_bad_json_then_good_json_is_accepted_on_the_second_try():
    result, llm = run(["Sure! Here you go:", reply()])
    assert result.status is VALID
    assert len(llm.calls) == 2


@pytest.mark.parametrize(
    "bad",
    [
        "not json at all",
        "[1, 2, 3]",
        '"just a string"',
        '{"quantity": "many"}',
        '{"quantity": -3}',
        '{"quantity": true}',
        '{"estimated_total": NaN}',
        "{" * 5000,
        # The same mistakes inside the extraction-v1 field objects.
        '{"quantity": {"status": "PRESENT", "value": "many"}}',
        '{"quantity": {"status": "PRESENT", "value": -3}}',
        '{"quantity": {"status": "PRESENT", "value": true}}',
        '{"quantity": {"status": "PRESENT", "value": 2.5}}',
        '{"estimated_total": {"status": "PRESENT", "value": NaN}}',
        '{"quantity": {"status": "MAYBE", "value": 3}}',
    ],
)
def test_unusable_output_twice_gives_invalid_not_a_crash(bad):
    result, llm = run([bad, bad])
    assert result.status is INVALID
    assert result.problems
    assert len(llm.calls) == 2
    assert result.estimated_total is None


def test_problems_never_contain_the_request_text():
    result, _ = run(['{"quantity": "many"}'] * 2)
    assert "office chairs" not in " ".join(result.problems)


# ---------- failures of the model service ----------


@pytest.mark.parametrize(
    "error",
    [
        LLMRequestFailed("down"),
        LLMRateLimited("slow down", 5),
        LLMAuthError("bad key"),
        RuntimeError("something unexpected"),
    ],
)
def test_model_failure_gives_failed_and_is_not_retried(error):
    result, llm = run([error, reply()])
    assert result.status is FAILED
    assert result.problems
    assert len(llm.calls) == 1


# ---------- bad request text ----------


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_empty_request_is_invalid_and_the_model_is_not_called(text):
    result, llm = run([reply()], text=text)
    assert result.status is INVALID
    assert llm.calls == []


def test_too_long_request_is_invalid_and_the_model_is_not_called():
    result, llm = run([reply()], text="x" * 5001)
    assert result.status is INVALID
    assert llm.calls == []


def test_the_length_limit_can_be_changed():
    result, llm = run([reply()], max_chars=20)
    assert result.status is INVALID
    assert llm.calls == []


def test_when_nothing_could_be_read_every_required_detail_is_reported_missing():
    for replies in (["nope", "nope"], [LLMRequestFailed("down")]):
        result, _ = run(replies)
        assert result.missing_fields == [
            "item_description", "quantity", "estimated_total", "currency", "business_justification",
        ]
