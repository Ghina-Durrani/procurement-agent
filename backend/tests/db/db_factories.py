"""Test data builders for the database tests. Synthetic data only."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import (
    Budget,
    Organization,
    ProcurementRequest,
    PurchaseOrder,
    Quotation,
    Supplier,
    User,
)
from app.models.enums import SupplierStatus


def make_org(session: Session) -> Organization:
    org = Organization(name=f"Org-{uuid.uuid4()}")
    session.add(org)
    session.flush()
    return org


def make_user(session: Session, org: Organization, role: str = "Requester") -> User:
    user = User(
        organization_id=org.id,
        email=f"{uuid.uuid4()}@example.test",
        full_name="Test User",
        role=role,
    )
    session.add(user)
    session.flush()
    return user


def make_request(
    session: Session, org: Organization, requester: User, **changes: Any
) -> ProcurementRequest:
    request = ProcurementRequest(
        organization_id=org.id,
        requester_id=requester.id,
        raw_message="Need 10 laptops",
        **changes,
    )
    session.add(request)
    session.flush()
    return request


def is_rejected(session: Session, *objects: Any) -> bool:
    """True if the database refuses to save these objects (the transaction stays usable)."""
    try:
        with session.begin_nested():
            session.add_all(objects)
            session.flush()
    except DBAPIError:
        return True
    return False


def config_json(org: Organization, policy_version: str) -> dict[str, str]:
    """The smallest JSON that satisfies the 'config matches its row' rule."""
    return {"organization_id": str(org.id), "policy_version": policy_version}


def make_supplier(
    session: Session,
    org: Organization,
    name: str | None = None,
    status: SupplierStatus = SupplierStatus.APPROVED,
) -> Supplier:
    supplier = Supplier(
        organization_id=org.id, name=name or f"Supplier-{uuid.uuid4()}", status=status
    )
    session.add(supplier)
    session.flush()
    return supplier


def make_budget(session: Session, org: Organization, **changes: Any) -> Budget:
    values: dict[str, Any] = {
        "name": f"Budget-{uuid.uuid4()}",
        "period_start": date(2026, 7, 1),
        "period_end": date(2027, 6, 30),
        "total_amount": Decimal("1000000.00"),
        "currency": "PKR",
    }
    values.update(changes)
    budget = Budget(organization_id=org.id, **values)
    session.add(budget)
    session.flush()
    return budget


def make_quotation(
    session: Session,
    org: Organization,
    request: ProcurementRequest,
    supplier: Supplier,
    **changes: Any,
) -> Quotation:
    values: dict[str, Any] = {"total_amount": Decimal("100000.00"), "currency": "PKR"}
    values.update(changes)
    quotation = Quotation(
        organization_id=org.id, request_id=request.id, supplier_id=supplier.id, **values
    )
    session.add(quotation)
    session.flush()
    return quotation


def purchase_order_for(
    org: Organization, request: ProcurementRequest, quotation: Quotation, **changes: Any
) -> PurchaseOrder:
    """A purchase order that copies its quotation and the request's approved amount."""
    values: dict[str, Any] = {
        "po_number": f"PO-{uuid.uuid4().hex[:8]}",
        "total_amount": quotation.total_amount,
        "currency": quotation.currency,
        "supplier_id": quotation.supplier_id,
        "approved_amount": request.approved_amount,
    }
    values.update(changes)
    return PurchaseOrder(
        organization_id=org.id, request_id=request.id, quotation_id=quotation.id, **values
    )
