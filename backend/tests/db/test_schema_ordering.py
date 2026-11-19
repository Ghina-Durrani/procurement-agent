"""Purchase orders: the database must refuse an order that breaks the approval trail."""
from decimal import Decimal

import pytest
import sqlalchemy as sa
from db_factories import (
    is_rejected,
    make_org,
    make_quotation,
    make_request,
    make_supplier,
    make_user,
    purchase_order_for,
)
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.enums import PurchaseOrderStatus

pytestmark = pytest.mark.integration


def ordering_setup(session: Session, *, approved="120000.00", quoted="100000.00"):
    """An approved request (ceiling 120,000) with one quotation (100,000)."""
    org = make_org(session)
    requester = make_user(session, org)
    request = make_request(
        session, org, requester, approved_amount=Decimal(approved) if approved else None
    )
    supplier = make_supplier(session, org)
    quotation = make_quotation(session, org, request, supplier, total_amount=Decimal(quoted))
    return org, request, supplier, quotation


def test_a_matching_purchase_order_is_accepted(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session)
    assert not is_rejected(session, purchase_order_for(org, request, quotation))


def test_a_po_total_that_differs_from_its_quotation_is_rejected(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session)
    assert is_rejected(
        session, purchase_order_for(org, request, quotation, total_amount=Decimal("99999.00"))
    )


def test_a_po_currency_that_differs_from_its_quotation_is_rejected(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session)
    assert is_rejected(session, purchase_order_for(org, request, quotation, currency="USD"))


def test_a_po_cannot_name_a_different_supplier_than_its_quotation(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session)
    other = make_supplier(session, org)
    assert is_rejected(session, purchase_order_for(org, request, quotation, supplier_id=other.id))


def test_a_po_cannot_use_a_quotation_of_a_different_request(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session)
    other_request = make_request(
        session, org, make_user(session, org), approved_amount=Decimal("120000.00")
    )
    wrong = purchase_order_for(org, other_request, quotation)
    assert is_rejected(session, wrong)


def test_a_po_above_the_approved_amount_is_rejected(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session, approved="120000.00", quoted="150000.00")
    assert is_rejected(session, purchase_order_for(org, request, quotation))


def test_a_po_exactly_at_the_approved_amount_is_accepted(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session, approved="100000.00", quoted="100000.00")
    assert not is_rejected(session, purchase_order_for(org, request, quotation))


def test_a_po_cannot_claim_a_higher_ceiling_than_the_request_has(session: Session) -> None:
    """Even with a high claimed ceiling, the foreign key checks it against the request."""
    org, request, _, quotation = ordering_setup(session, approved="120000.00", quoted="150000.00")
    wrong = purchase_order_for(org, request, quotation, approved_amount=Decimal("150000.00"))
    assert is_rejected(session, wrong)


def test_a_po_for_a_request_with_no_approved_amount_is_rejected(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session, approved=None)
    wrong = purchase_order_for(org, request, quotation, approved_amount=Decimal("100000.00"))
    assert is_rejected(session, wrong)


def test_a_po_cannot_use_a_quotation_of_another_organization(session: Session) -> None:
    org_a, request_a, _, _ = ordering_setup(session)
    _, _, _, quotation_b = ordering_setup(session)
    assert is_rejected(session, purchase_order_for(org_a, request_a, quotation_b))


def test_a_request_cannot_have_two_live_purchase_orders(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session)
    session.add(purchase_order_for(org, request, quotation))
    session.flush()
    assert is_rejected(session, purchase_order_for(org, request, quotation))


def test_a_new_po_is_allowed_after_the_first_is_cancelled(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session)
    first = purchase_order_for(org, request, quotation)
    session.add(first)
    session.flush()
    first.status = PurchaseOrderStatus.CANCELLED
    session.flush()
    assert not is_rejected(session, purchase_order_for(org, request, quotation))


def test_a_po_number_cannot_repeat_within_an_organization(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session)
    session.add(purchase_order_for(org, request, quotation, po_number="PO-1"))
    session.flush()
    other_request = make_request(
        session, org, make_user(session, org), approved_amount=Decimal("120000.00")
    )
    other_quotation = make_quotation(session, org, other_request, make_supplier(session, org))
    assert is_rejected(
        session, purchase_order_for(org, other_request, other_quotation, po_number="PO-1")
    )


def test_an_issued_po_must_record_who_issued_it(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session)
    assert is_rejected(
        session, purchase_order_for(org, request, quotation, status=PurchaseOrderStatus.ISSUED)
    )


def test_a_quotation_cannot_change_its_total_once_an_order_exists(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session)
    session.add(purchase_order_for(org, request, quotation))
    session.flush()
    with pytest.raises(DBAPIError):
        with session.begin_nested():
            session.execute(
                sa.text("UPDATE quotations SET total_amount = 1.00 WHERE id = :id"),
                {"id": quotation.id},
            )


def test_a_request_cannot_lower_its_ceiling_once_an_order_exists(session: Session) -> None:
    org, request, _, quotation = ordering_setup(session)
    session.add(purchase_order_for(org, request, quotation))
    session.flush()
    with pytest.raises(DBAPIError):
        with session.begin_nested():
            session.execute(
                sa.text("UPDATE procurement_requests SET approved_amount = 1.00 WHERE id = :id"),
                {"id": request.id},
            )
