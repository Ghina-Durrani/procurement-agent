"""Reading rules from challenge run 1 (D-063), through the same path the web app uses.

POST /api/v1/requests → saved → extraction (scripted fake AI) → evidence checks → policy
engine → saved decision. Ordinary requests that must still pass are tested next to each fix.
"""
import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from app.services.extraction import scripted_reply
from app.services.intake.seed_demo import seed
from tests.api.conftest import ScriptedAI

pytestmark = pytest.mark.integration

URL = "/api/v1/requests"


@pytest.fixture()
def employee(session: Session, act_as) -> User:  # type: ignore[no-untyped-def]
    user = seed(session, f"demo-{uuid.uuid4().hex[:8]}@example.test")
    act_as(user)
    return user


def _submit(client: TestClient, text: str) -> dict[str, Any]:
    response = client.post(URL, json={"message": text})
    assert response.status_code == 201, response.text
    return response.json()


def _rules(body: dict[str, Any]) -> list[str]:
    return sorted({rule["rule_id"] for rule in body["decision"]["triggered_rules"]})


def _reply(values: dict[str, Any], evidence: dict[str, str], **extra: Any) -> str:
    return scripted_reply(values, evidence, **extra)


# --- CH-005: an amount written in words --------------------------------------------------

DESKS = "Buy 3 desks for the new finance cabin, forty-nine thousand five hundred rupees altogether."
DESK_VALUES = {"item_description": "desks", "quantity": 3, "estimated_total": "49500", "currency": "PKR",
               "item_category": "FURNITURE", "business_justification": "for the new finance cabin"}
DESK_EVIDENCE = {"item_description": "desks", "quantity": "3 desks",
                 "estimated_total": "forty-nine thousand five hundred rupees", "currency": "rupees",
                 "item_category": "desks", "business_justification": "for the new finance cabin"}


def test_amount_in_words_is_accepted(client: TestClient, ai: ScriptedAI, employee: User) -> None:
    ai.script(_reply(DESK_VALUES, DESK_EVIDENCE))
    body = _submit(client, DESKS)
    assert body["outcome"] == "CONTINUE"
    assert body["status"] == "APPROVED"
    total = next(f for f in body["fields"] if f["name"] == "estimated_total")
    assert total == {"name": "estimated_total", "status": "PRESENT", "value": "49500"}


def test_amount_in_words_that_disagrees_is_not_accepted(client: TestClient, ai: ScriptedAI, employee: User) -> None:
    ai.script(_reply({**DESK_VALUES, "estimated_total": "4950"}, DESK_EVIDENCE))
    body = _submit(client, DESKS)
    assert body["outcome"] == "HUMAN_REVIEW"


def test_lakh_in_words_and_digits_still_work(client: TestClient, ai: ScriptedAI, employee: User) -> None:
    text = "Buy 3 desks for the new finance cabin, Rs 1.2 lakh altogether."
    ai.script(_reply({**DESK_VALUES, "estimated_total": "120000"},
                     {**DESK_EVIDENCE, "estimated_total": "Rs 1.2 lakh", "currency": "Rs"}))
    body = _submit(client, text)
    total = next(f for f in body["fields"] if f["name"] == "estimated_total")
    assert total["status"] == "PRESENT" and total["value"] == "120000"


# --- CH-016: a supplier correction; open alternatives stay ambiguous ----------------------

CHAIRS = "Order 4 office chairs from Metro Furniture, total Rs 28,000. Actually, please order them from Office Mart instead."
CHAIR_VALUES = {"item_description": "office chairs", "quantity": 4, "estimated_total": "28000", "currency": "PKR",
                "item_category": "FURNITURE", "supplier_name": "Office Mart"}
CHAIR_EVIDENCE = {"item_description": "office chairs", "quantity": "4 office chairs", "estimated_total": "Rs 28,000",
                  "currency": "Rs", "item_category": "office chairs",
                  "supplier_name": "please order them from Office Mart instead"}


def test_supplier_correction_read_as_present_continues(client: TestClient, ai: ScriptedAI, employee: User) -> None:
    ai.script(_reply(CHAIR_VALUES, CHAIR_EVIDENCE))
    body = _submit(client, CHAIRS)
    assert body["outcome"] == "CONTINUE"
    supplier = next(f for f in body["fields"] if f["name"] == "supplier_name")
    assert supplier["value"] == "Office Mart"


def test_open_alternatives_stay_ambiguous(client: TestClient, ai: ScriptedAI, employee: User) -> None:
    text = "Order 4 office chairs, Rs 28,000, from Metro Furniture or Office Mart, whichever is cheaper."
    reply = json.loads(_reply({k: v for k, v in CHAIR_VALUES.items() if k != "supplier_name"},
                              {k: v for k, v in CHAIR_EVIDENCE.items() if k != "supplier_name"}))
    reply["supplier_name"] = {"status": "AMBIGUOUS", "value": None, "evidence": "Metro Furniture or Office Mart"}
    ai.script(json.dumps(reply))
    body = _submit(client, text)
    supplier = next(f for f in body["fields"] if f["name"] == "supplier_name")
    assert supplier["status"] == "AMBIGUOUS" and supplier["value"] is None
    assert "POL-005" not in _rules(body)  # both options are approved; sourcing picks later


# --- CH-032 / Q-010: a different company to invoice or be paid ----------------------------

KEYBOARDS = "Order 3 keyboards from TechZone, Rs 9,000, for the new hires. The invoice should come from Rehman Computers."
KB_VALUES = {"item_description": "keyboards", "quantity": 3, "estimated_total": "9000", "currency": "PKR",
             "item_category": "IT_HARDWARE", "supplier_name": "TechZone", "business_justification": "for the new hires"}
KB_EVIDENCE = {"item_description": "keyboards", "quantity": "3 keyboards", "estimated_total": "Rs 9,000",
               "currency": "Rs", "item_category": "keyboards", "supplier_name": "TechZone",
               "business_justification": "for the new hires"}


def test_low_value_request_with_another_invoice_company_goes_to_review(
    client: TestClient, ai: ScriptedAI, employee: User
) -> None:
    ai.script(_reply(KB_VALUES, KB_EVIDENCE, payment_party={"order_from": "TechZone", "invoice_or_payment": "Rehman Computers"}))
    body = _submit(client, KEYBOARDS)
    assert body["outcome"] == "HUMAN_REVIEW"
    assert body["status"] == "AWAITING_APPROVAL"
    assert _rules(body) == ["POL-005"]  # Rs 9,000: nothing else would ask a person
    reason = body["decision"]["triggered_rules"][0]["reason"]
    assert "TechZone" in reason and "Rehman Computers" in reason
    supplier = next(f for f in body["fields"] if f["name"] == "supplier_name")
    assert supplier["status"] == "CONFLICTING" and supplier["value"] is None


def test_payment_to_another_company_goes_to_review(client: TestClient, ai: ScriptedAI, employee: User) -> None:
    text = "Order 3 keyboards from TechZone, Rs 9,000, for the new hires. Please pay Rehman Computers directly."
    ai.script(_reply(KB_VALUES, KB_EVIDENCE, payment_party={"order_from": "TechZone", "invoice_or_payment": "Rehman Computers"}))
    assert _rules(_submit(client, text)) == ["POL-005"]


def test_different_delivery_recipient_alone_is_normal(client: TestClient, ai: ScriptedAI, employee: User) -> None:
    text = "Order 3 keyboards from TechZone, Rs 9,000, for the new hires. Deliver them to Rehman Computers for setup."
    ai.script(_reply(KB_VALUES, KB_EVIDENCE, payment_party={"order_from": "TechZone", "invoice_or_payment": None}))
    body = _submit(client, text)
    assert body["outcome"] == "CONTINUE"


def test_invoice_from_the_same_supplier_is_normal(client: TestClient, ai: ScriptedAI, employee: User) -> None:
    text = "Order 3 keyboards from TechZone, Rs 9,000, for the new hires. The invoice should come from techzone."
    ai.script(_reply(KB_VALUES, KB_EVIDENCE, payment_party={"order_from": "TechZone", "invoice_or_payment": "techzone"}))
    assert _submit(client, text)["outcome"] == "CONTINUE"


def test_made_up_invoice_company_is_ignored(client: TestClient, ai: ScriptedAI, employee: User) -> None:
    # The quote must be real text: the AI cannot invent a conflict (or a name) on its own.
    text = "Order 3 keyboards from TechZone, Rs 9,000, for the new hires."
    ai.script(_reply(KB_VALUES, KB_EVIDENCE, payment_party={"order_from": "TechZone", "invoice_or_payment": "Rehman Computers"}))
    assert _submit(client, text)["outcome"] == "CONTINUE"


def test_ordinary_request_still_continues(client: TestClient, ai: ScriptedAI, employee: User) -> None:
    text = "Order 3 keyboards from TechZone, Rs 9,000, for the new hires."
    ai.script(_reply(KB_VALUES, KB_EVIDENCE))
    body = _submit(client, text)
    assert (body["outcome"], body["status"]) == ("CONTINUE", "APPROVED")
