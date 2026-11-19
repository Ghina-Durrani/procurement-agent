"""RFQs, documents, quotations, quotation lines and supplier evaluations."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from db_factories import (
    is_rejected,
    make_org,
    make_quotation,
    make_request,
    make_supplier,
    make_user,
)
from sqlalchemy.orm import Session

from app.models import Document, Quotation, QuotationItem, Rfq, RfqSupplier, SupplierEvaluation
from app.models.enums import ExtractionStatus, QuotationSource, RfqStatus

pytestmark = pytest.mark.integration


def setup_request(session: Session):
    org = make_org(session)
    user = make_user(session, org)
    return org, user, make_request(session, org, user)


# ---- RFQs -------------------------------------------------------------------
def test_a_draft_rfq_needs_no_sent_time(session: Session) -> None:
    org, _, request = setup_request(session)
    rfq = Rfq(organization_id=org.id, request_id=request.id, subject="RFQ", body="Please quote")
    assert not is_rejected(session, rfq)


def test_a_sent_rfq_must_record_when_it_was_sent(session: Session) -> None:
    org, _, request = setup_request(session)
    sent = Rfq(
        organization_id=org.id,
        request_id=request.id,
        subject="RFQ",
        body="Please quote",
        status=RfqStatus.SENT,
    )
    assert is_rejected(session, sent)


def test_a_sent_rfq_with_a_time_is_accepted(session: Session) -> None:
    org, _, request = setup_request(session)
    sent = Rfq(
        organization_id=org.id,
        request_id=request.id,
        subject="RFQ",
        body="Please quote",
        status=RfqStatus.SENT,
        sent_at=datetime.now(timezone.utc),
    )
    assert not is_rejected(session, sent)


def test_an_rfq_cannot_be_linked_to_a_request_of_another_organization(session: Session) -> None:
    org_a, _, _ = setup_request(session)
    _, _, request_b = setup_request(session)
    assert is_rejected(
        session, Rfq(organization_id=org_a.id, request_id=request_b.id, subject="x", body="x")
    )


def make_rfq(session: Session, org, request) -> Rfq:
    rfq = Rfq(organization_id=org.id, request_id=request.id, subject="RFQ", body="Please quote")
    session.add(rfq)
    session.flush()
    return rfq


def test_a_supplier_cannot_be_invited_twice_to_the_same_rfq(session: Session) -> None:
    org, _, request = setup_request(session)
    rfq, supplier = make_rfq(session, org, request), make_supplier(session, org)
    session.add(RfqSupplier(organization_id=org.id, rfq_id=rfq.id, supplier_id=supplier.id))
    session.flush()
    assert is_rejected(
        session, RfqSupplier(organization_id=org.id, rfq_id=rfq.id, supplier_id=supplier.id)
    )


def test_an_rfq_cannot_invite_a_supplier_of_another_organization(session: Session) -> None:
    org, _, request = setup_request(session)
    rfq = make_rfq(session, org, request)
    foreign = make_supplier(session, make_org(session))
    assert is_rejected(
        session, RfqSupplier(organization_id=org.id, rfq_id=rfq.id, supplier_id=foreign.id)
    )


# ---- documents --------------------------------------------------------------
def make_document(org, request, **changes) -> Document:
    values = {
        "original_filename": "quote.pdf",
        "content_type": "application/pdf",
        "size_bytes": 2048,
        "sha256": "a" * 64,
        "storage_key": f"docs/{uuid.uuid4()}",
        **changes,
    }
    return Document(organization_id=org.id, request_id=request.id, **values)


def test_a_valid_document_record_is_accepted(session: Session) -> None:
    org, _, request = setup_request(session)
    assert not is_rejected(session, make_document(org, request))


@pytest.mark.parametrize(
    "changes",
    [
        {"size_bytes": 0},
        {"size_bytes": 10485761},
        {"sha256": "abc"},
    ],
    ids=["empty file", "over 10 MB", "short checksum"],
)
def test_invalid_document_records_are_rejected(session: Session, changes: dict) -> None:
    org, _, request = setup_request(session)
    assert is_rejected(session, make_document(org, request, **changes))


def test_a_storage_key_cannot_be_reused(session: Session) -> None:
    org, _, request = setup_request(session)
    session.add(make_document(org, request, storage_key="docs/same"))
    session.flush()
    assert is_rejected(session, make_document(org, request, storage_key="docs/same"))


def test_a_document_cannot_belong_to_a_request_of_another_organization(
    session: Session,
) -> None:
    org_a, _, _ = setup_request(session)
    _, _, request_b = setup_request(session)
    assert is_rejected(session, make_document(org_a, request_b))


# ---- quotations -------------------------------------------------------------
def test_a_valid_quotation_is_accepted(session: Session) -> None:
    org, _, request = setup_request(session)
    quotation = make_quotation(session, org, request, make_supplier(session, org))
    session.refresh(quotation)
    assert quotation.is_selected is False and quotation.needs_verification is False


def test_a_supplier_can_quote_only_once_per_request(session: Session) -> None:
    org, _, request = setup_request(session)
    supplier = make_supplier(session, org)
    make_quotation(session, org, request, supplier)
    assert is_rejected(
        session,
        Quotation(
            organization_id=org.id,
            request_id=request.id,
            supplier_id=supplier.id,
            total_amount=Decimal("1.00"),
            currency="PKR",
        ),
    )


def test_a_quotation_cannot_use_a_supplier_of_another_organization(session: Session) -> None:
    org, _, request = setup_request(session)
    foreign = make_supplier(session, make_org(session))
    assert is_rejected(
        session,
        Quotation(
            organization_id=org.id,
            request_id=request.id,
            supplier_id=foreign.id,
            total_amount=Decimal("1.00"),
            currency="PKR",
        ),
    )


def test_a_quotation_must_state_its_currency(session: Session) -> None:
    org, _, request = setup_request(session)
    supplier = make_supplier(session, org)
    assert is_rejected(
        session,
        Quotation(
            organization_id=org.id,
            request_id=request.id,
            supplier_id=supplier.id,
            total_amount=Decimal("1.00"),
        ),
    )


def test_a_negative_quotation_total_is_rejected(session: Session) -> None:
    org, _, request = setup_request(session)
    supplier = make_supplier(session, org)
    assert is_rejected(
        session,
        Quotation(
            organization_id=org.id,
            request_id=request.id,
            supplier_id=supplier.id,
            total_amount=Decimal("-1.00"),
            currency="PKR",
        ),
    )


def test_only_one_quotation_can_be_selected_per_request(session: Session) -> None:
    org, _, request = setup_request(session)
    make_quotation(session, org, request, make_supplier(session, org), is_selected=True)
    other = make_supplier(session, org)
    assert is_rejected(
        session,
        Quotation(
            organization_id=org.id,
            request_id=request.id,
            supplier_id=other.id,
            total_amount=Decimal("1.00"),
            currency="PKR",
            is_selected=True,
        ),
    )


def test_a_quotation_waiting_for_verification_cannot_be_selected(session: Session) -> None:
    org, _, request = setup_request(session)
    supplier = make_supplier(session, org)
    assert is_rejected(
        session,
        Quotation(
            organization_id=org.id,
            request_id=request.id,
            supplier_id=supplier.id,
            total_amount=Decimal("1.00"),
            currency="PKR",
            needs_verification=True,
            is_selected=True,
        ),
    )


@pytest.mark.parametrize("status", [ExtractionStatus.INVALID, ExtractionStatus.FAILED])
def test_a_badly_extracted_quotation_cannot_be_selected(
    session: Session, status: ExtractionStatus
) -> None:
    org, _, request = setup_request(session)
    supplier = make_supplier(session, org)
    assert is_rejected(
        session,
        Quotation(
            organization_id=org.id,
            request_id=request.id,
            supplier_id=supplier.id,
            total_amount=Decimal("1.00"),
            currency="PKR",
            source=QuotationSource.EXTRACTED,
            extraction_status=status,
            is_selected=True,
        ),
    )


def test_a_validly_extracted_quotation_can_be_selected(session: Session) -> None:
    org, _, request = setup_request(session)
    supplier = make_supplier(session, org)
    assert not is_rejected(
        session,
        Quotation(
            organization_id=org.id,
            request_id=request.id,
            supplier_id=supplier.id,
            total_amount=Decimal("1.00"),
            currency="PKR",
            source=QuotationSource.EXTRACTED,
            extraction_status=ExtractionStatus.VALID,
            is_selected=True,
        ),
    )


def test_an_extracted_quotation_must_record_its_extraction_status(session: Session) -> None:
    org, _, request = setup_request(session)
    supplier = make_supplier(session, org)
    assert is_rejected(
        session,
        Quotation(
            organization_id=org.id,
            request_id=request.id,
            supplier_id=supplier.id,
            total_amount=Decimal("1.00"),
            currency="PKR",
            source=QuotationSource.EXTRACTED,
        ),
    )


# ---- quotation lines --------------------------------------------------------
def make_line(org, quotation, **changes) -> QuotationItem:
    values = {
        "line_number": 1,
        "description": "Laptop",
        "quantity": 10,
        "unit_price": Decimal("95000.00"),
        "line_total": Decimal("950000.00"),
        **changes,
    }
    return QuotationItem(organization_id=org.id, quotation_id=quotation.id, **values)


def test_a_correct_quotation_line_is_accepted(session: Session) -> None:
    org, _, request = setup_request(session)
    quotation = make_quotation(session, org, request, make_supplier(session, org))
    assert not is_rejected(session, make_line(org, quotation))


def test_a_line_total_that_is_not_quantity_times_price_is_rejected(session: Session) -> None:
    org, _, request = setup_request(session)
    quotation = make_quotation(session, org, request, make_supplier(session, org))
    assert is_rejected(session, make_line(org, quotation, line_total=Decimal("950000.01")))


@pytest.mark.parametrize("changes", [{"quantity": 0, "line_total": Decimal("0")},
                                     {"line_number": 0},
                                     {"unit_price": Decimal("-1"), "line_total": Decimal("-10")}],
                         ids=["zero quantity", "line zero", "negative price"])
def test_invalid_quotation_lines_are_rejected(session: Session, changes: dict) -> None:
    org, _, request = setup_request(session)
    quotation = make_quotation(session, org, request, make_supplier(session, org))
    assert is_rejected(session, make_line(org, quotation, **changes))


def test_a_line_number_cannot_repeat_within_a_quotation(session: Session) -> None:
    org, _, request = setup_request(session)
    quotation = make_quotation(session, org, request, make_supplier(session, org))
    session.add(make_line(org, quotation))
    session.flush()
    assert is_rejected(session, make_line(org, quotation))


# ---- supplier evaluation ----------------------------------------------------
def make_evaluation_row(org, request, quotation, **changes) -> SupplierEvaluation:
    values = {
        "rank": 1,
        "total_score": Decimal("87.50"),
        "criteria_scores": {"price": 90, "delivery": 85},
        "rationale": "Lowest price, good delivery",
        "method_version": "v1",
        **changes,
    }
    return SupplierEvaluation(
        organization_id=org.id, request_id=request.id, quotation_id=quotation.id, **values
    )


def test_a_valid_supplier_evaluation_is_accepted(session: Session) -> None:
    org, _, request = setup_request(session)
    quotation = make_quotation(session, org, request, make_supplier(session, org))
    assert not is_rejected(session, make_evaluation_row(org, request, quotation))


@pytest.mark.parametrize("changes", [{"rank": 0}, {"total_score": Decimal("100.01")},
                                     {"total_score": Decimal("-0.01")}],
                         ids=["rank zero", "score above 100", "negative score"])
def test_invalid_supplier_evaluations_are_rejected(session: Session, changes: dict) -> None:
    org, _, request = setup_request(session)
    quotation = make_quotation(session, org, request, make_supplier(session, org))
    assert is_rejected(session, make_evaluation_row(org, request, quotation, **changes))


def test_an_evaluation_cannot_score_a_quotation_of_another_organization(
    session: Session,
) -> None:
    org_a, _, request_a = setup_request(session)
    org_b, _, request_b = setup_request(session)
    quotation_b = make_quotation(session, org_b, request_b, make_supplier(session, org_b))
    assert is_rejected(session, make_evaluation_row(org_a, request_a, quotation_b))
