"""Suppliers, supplier categories, budgets and approvals."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from db_factories import (
    is_rejected,
    make_budget,
    make_org,
    make_supplier,
    make_user,
)
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_schema import make_evaluation

from app.models import Approval, Budget, ProcurementRequest, Supplier, SupplierCategory
from app.models.enums import ApprovalDecision, SupplierStatus

pytestmark = pytest.mark.integration


# ---- suppliers --------------------------------------------------------------
def test_a_new_supplier_is_not_approved_by_default(session: Session) -> None:
    org = make_org(session)
    supplier = Supplier(organization_id=org.id, name="Fresh Supplier")
    session.add(supplier)
    session.flush()
    session.refresh(supplier)
    assert supplier.status is SupplierStatus.NOT_APPROVED


def test_supplier_names_are_unique_ignoring_case(session: Session) -> None:
    org = make_org(session)
    make_supplier(session, org, name="TechZone")
    assert is_rejected(session, Supplier(organization_id=org.id, name="techzone"))


def test_two_organizations_can_have_a_supplier_with_the_same_name(session: Session) -> None:
    make_supplier(session, make_org(session), name="TechZone")
    assert not is_rejected(session, Supplier(organization_id=make_org(session).id, name="TechZone"))


def test_every_supplier_status_of_the_engine_is_accepted(session: Session) -> None:
    org = make_org(session)
    for status in SupplierStatus:
        make_supplier(session, org, status=status)  # flush raises if a value is rejected


def test_a_supplier_category_cannot_be_listed_twice(session: Session) -> None:
    org = make_org(session)
    supplier = make_supplier(session, org)
    session.add(
        SupplierCategory(organization_id=org.id, supplier_id=supplier.id, category="IT_HARDWARE")
    )
    session.flush()
    assert is_rejected(
        session,
        SupplierCategory(organization_id=org.id, supplier_id=supplier.id, category="IT_HARDWARE"),
    )


def test_a_category_must_be_uppercase_like_the_policy_lists(session: Session) -> None:
    org = make_org(session)
    supplier = make_supplier(session, org)
    assert is_rejected(
        session,
        SupplierCategory(organization_id=org.id, supplier_id=supplier.id, category="it_hardware"),
    )


def test_a_category_cannot_attach_to_a_supplier_of_another_organization(
    session: Session,
) -> None:
    org_a, org_b = make_org(session), make_org(session)
    supplier_b = make_supplier(session, org_b)
    assert is_rejected(
        session,
        SupplierCategory(organization_id=org_a.id, supplier_id=supplier_b.id, category="TRAVEL"),
    )


# ---- budgets ----------------------------------------------------------------
def test_a_budget_cannot_promise_more_money_than_it_has(session: Session) -> None:
    org = make_org(session)
    over = Budget(
        organization_id=org.id,
        name="Over",
        period_start=datetime(2026, 7, 1).date(),
        period_end=datetime(2027, 6, 30).date(),
        total_amount=Decimal("1000.00"),
        committed_amount=Decimal("1000.01"),
        currency="PKR",
    )
    assert is_rejected(session, over)


def test_a_budget_can_be_fully_committed(session: Session) -> None:
    org = make_org(session)
    make_budget(
        session, org, total_amount=Decimal("1000.00"), committed_amount=Decimal("1000.00")
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"total_amount": Decimal("-1.00")},
        {"committed_amount": Decimal("-1.00")},
        {"finance_review_above": Decimal("-1.00")},
        {"currency": None},
    ],
    ids=["negative total", "negative committed", "negative threshold", "currency missing"],
)
def test_invalid_budget_values_are_rejected(session: Session, changes: dict) -> None:
    org = make_org(session)
    with pytest.raises(DBAPIError):
        with session.begin_nested():
            make_budget(session, org, **changes)


def test_a_budget_cannot_end_before_it_starts(session: Session) -> None:
    org = make_org(session)
    with pytest.raises(DBAPIError):
        with session.begin_nested():
            make_budget(
                session,
                org,
                period_start=datetime(2026, 12, 1).date(),
                period_end=datetime(2026, 1, 1).date(),
            )


def test_a_request_cannot_use_a_budget_of_another_organization(session: Session) -> None:
    org_a, org_b = make_org(session), make_org(session)
    budget_b = make_budget(session, org_b)
    wrong = ProcurementRequest(
        organization_id=org_a.id,
        requester_id=make_user(session, org_a).id,
        raw_message="x",
        budget_id=budget_b.id,
    )
    assert is_rejected(session, wrong)


# ---- approvals --------------------------------------------------------------
def make_approval(org, request, evaluation, **changes) -> Approval:
    values = {"required_role": "Manager", **changes}
    return Approval(
        organization_id=org.id,
        request_id=request.id,
        policy_evaluation_id=evaluation.id,
        **values,
    )


def test_a_pending_approval_can_be_saved_and_then_decided(session: Session) -> None:
    org, request, evaluation = make_evaluation(session)
    manager = make_user(session, org, "Manager")
    approval = make_approval(org, request, evaluation)
    session.add(approval)
    session.flush()
    approval.decision = ApprovalDecision.APPROVED
    approval.decided_by_user_id = manager.id
    approval.decided_at = datetime.now(timezone.utc)
    approval.approved_amount = Decimal("50000.00")
    session.flush()  # a valid decision is accepted


def test_a_decision_without_a_decider_is_rejected(session: Session) -> None:
    org, request, evaluation = make_evaluation(session)
    assert is_rejected(
        session, make_approval(org, request, evaluation, decision=ApprovalDecision.APPROVED)
    )


def test_a_pending_approval_cannot_already_have_a_decider(session: Session) -> None:
    org, request, evaluation = make_evaluation(session)
    manager = make_user(session, org, "Manager")
    assert is_rejected(
        session,
        make_approval(
            org,
            request,
            evaluation,
            decided_by_user_id=manager.id,
            decided_at=datetime.now(timezone.utc),
        ),
    )


def test_a_rejected_approval_cannot_carry_an_approved_amount(session: Session) -> None:
    org, request, evaluation = make_evaluation(session)
    manager = make_user(session, org, "Manager")
    assert is_rejected(
        session,
        make_approval(
            org,
            request,
            evaluation,
            decision=ApprovalDecision.REJECTED,
            decided_by_user_id=manager.id,
            decided_at=datetime.now(timezone.utc),
            approved_amount=Decimal("1.00"),
        ),
    )


def test_one_role_is_asked_only_once_per_evaluation(session: Session) -> None:
    org, request, evaluation = make_evaluation(session)
    session.add(make_approval(org, request, evaluation))
    session.flush()
    assert is_rejected(session, make_approval(org, request, evaluation))


def test_an_approval_cannot_use_an_evaluation_of_another_organization(session: Session) -> None:
    org_a, request_a, _ = make_evaluation(session)
    _, _, evaluation_b = make_evaluation(session)
    assert is_rejected(session, make_approval(org_a, request_a, evaluation_b))


def test_a_negative_approved_amount_on_a_request_is_rejected(session: Session) -> None:
    org = make_org(session)
    assert is_rejected(
        session,
        ProcurementRequest(
            organization_id=org.id,
            requester_id=make_user(session, org).id,
            raw_message="x",
            approved_amount=Decimal("-1.00"),
        ),
    )
