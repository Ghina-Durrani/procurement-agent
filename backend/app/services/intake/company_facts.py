"""Trusted company facts for the policy engine, read from the database (never from the AI).

These are the app's version of evaluation/cases/context.json: the active policy settings,
the supplier list, the budget and the requester's recent requests. Every query is scoped by
the requester's organization. Anything missing or unclear returns None, and the engine then
fails closed (POL-900 for settings, POL-007 for budget).
"""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, PolicyConfig as PolicyConfigRow, ProcurementRequest, Supplier
from app.policy import BudgetStatus, PolicyConfig, RecentRequest, SupplierStatus


def active_policy(db: Session, organization_id: uuid.UUID) -> tuple[PolicyConfig, uuid.UUID] | None:
    """The organization's active settings and their row id, or None if absent or invalid."""
    row = db.scalars(
        select(PolicyConfigRow).where(
            PolicyConfigRow.organization_id == organization_id, PolicyConfigRow.is_active
        )
    ).one_or_none()
    if row is None:
        return None
    try:
        config = PolicyConfig.model_validate(row.config)
    except ValidationError:
        return None
    if config.organization_id != organization_id:
        return None
    return config, row.id


def _normalise(name: str) -> str:
    # Same rule as the experiment's lookup: ignore case and extra spaces.
    return " ".join(name.split()).casefold()


def supplier_status(
    db: Session, organization_id: uuid.UUID, name: str | None
) -> SupplierStatus | None:
    """None when no supplier is named; NOT_APPROVED when the name is not on the list."""
    if name is None or not name.strip():
        return None
    key = _normalise(name)
    statuses = {
        supplier.status
        for supplier in db.scalars(select(Supplier).where(Supplier.organization_id == organization_id))
        if _normalise(supplier.name) == key
    }
    if SupplierStatus.BLOCKED in statuses:  # a blocked entry always wins
        return SupplierStatus.BLOCKED
    if SupplierStatus.APPROVED in statuses:
        return SupplierStatus.APPROVED
    return SupplierStatus.NOT_APPROVED


def blocked_supplier_names(db: Session, organization_id: uuid.UUID) -> list[str]:
    """This organization's blocked suppliers, to spot them among open alternatives (D-062)."""
    return list(
        db.scalars(
            select(Supplier.name).where(
                Supplier.organization_id == organization_id,
                Supplier.status == SupplierStatus.BLOCKED,
            )
        )
    )


def budget_status(
    db: Session,
    organization_id: uuid.UUID,
    amount: Decimal | None,
    currency: str | None,
    on: date,
) -> BudgetStatus | None:
    """Read-only check against the one budget covering this date and currency.

    Nothing is reserved here; reserving money belongs to the later finance step. No amount,
    no budget, or more than one matching budget gives None, so the engine asks for review.
    """
    if amount is None or not currency:
        return None
    budgets = db.scalars(
        select(Budget).where(
            Budget.organization_id == organization_id,
            Budget.currency == currency.upper(),
            Budget.period_start <= on,
            Budget.period_end >= on,
        )
    ).all()
    if len(budgets) != 1:
        return None
    budget = budgets[0]
    if amount > budget.total_amount - budget.committed_amount:
        return BudgetStatus.INSUFFICIENT
    if budget.finance_review_above is not None and amount > budget.finance_review_above:
        return BudgetStatus.NEEDS_FINANCE_APPROVAL
    return BudgetStatus.AVAILABLE


def recent_requests(
    db: Session, request: ProcurementRequest, window_days: int
) -> list[RecentRequest]:
    """The requester's other requests in the split-purchase window (POL-004)."""
    since: datetime = request.submitted_at - timedelta(days=window_days)
    rows = db.scalars(
        select(ProcurementRequest).where(
            ProcurementRequest.organization_id == request.organization_id,
            ProcurementRequest.requester_id == request.requester_id,
            ProcurementRequest.id != request.id,
            ProcurementRequest.submitted_at >= since,
            ProcurementRequest.estimated_amount.is_not(None),
            ProcurementRequest.currency.is_not(None),
        )
    ).all()
    return [
        RecentRequest(
            request_id=row.id,
            submitted_at=row.submitted_at,
            estimated_total=row.estimated_amount,
            currency=row.currency,
            status=row.status.value,
            supplier_name=row.supplier_name,
            item_category=row.category,
        )
        for row in rows
        if row.estimated_amount is not None and row.currency is not None
    ]
