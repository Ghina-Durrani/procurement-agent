"""Reference data the policy rules read: suppliers, the categories they serve, budgets."""
import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    Money,
    created_at_col,
    enum_type,
    same_org_fk,
    updated_at_col,
    uuid_pk,
)
from app.models.enums import SupplierStatus


class Supplier(Base):
    """A supplier the organization knows. Its status feeds rule POL-005."""

    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(200))
    # A new supplier is NOT approved until a person approves it. Never default to APPROVED.
    status: Mapped[SupplierStatus] = mapped_column(
        enum_type(SupplierStatus, "supplier_status"), default=SupplierStatus.NOT_APPROVED
    )
    contact_email: Mapped[str | None] = mapped_column(sa.String(320))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        sa.UniqueConstraint("organization_id", "id", name="uq_suppliers_org_id_id"),
        # The policy engine compares supplier names ignoring case, so the database must too.
        sa.Index(
            "uq_suppliers_org_lower_name", "organization_id", sa.text("lower(name)"), unique=True
        ),
    )


class SupplierCategory(Base):
    """Which item categories a supplier serves. Used by supplier sourcing."""

    __tablename__ = "supplier_categories"

    supplier_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("organizations.id"))

    __table_args__ = (
        same_org_fk("supplier_id", "suppliers", "fk_supplier_categories_supplier_same_org"),
        sa.CheckConstraint("category = upper(category)", name="category_uppercase"),
        sa.Index("ix_supplier_categories_org_category", "organization_id", "category"),
    )


class Budget(Base):
    """Money available for a period. Feeds the finance check and rule POL-007."""

    __tablename__ = "budgets"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(200))
    period_start: Mapped[date]
    period_end: Mapped[date]
    total_amount: Mapped[Decimal] = mapped_column(Money)
    # Money already promised to approved purchases. Available = total - committed.
    committed_amount: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), server_default="0"
    )
    # Requests above this amount need Finance approval even when budget is available
    # (this is what produces NEEDS_FINANCE_APPROVAL). NULL means no such threshold.
    finance_review_above: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(sa.String(3))  # no default: be explicit
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        sa.UniqueConstraint("organization_id", "id", name="uq_budgets_org_id_id"),
        sa.UniqueConstraint(
            "organization_id", "name", "period_start", name="uq_budgets_org_id_name_period"
        ),
        sa.CheckConstraint("total_amount >= 0", name="total_non_negative"),
        sa.CheckConstraint("committed_amount >= 0", name="committed_non_negative"),
        # Hard guarantee: even buggy code cannot promise more money than the budget has.
        sa.CheckConstraint("committed_amount <= total_amount", name="not_overcommitted"),
        sa.CheckConstraint(
            "finance_review_above IS NULL OR finance_review_above >= 0",
            name="finance_threshold_non_negative",
        ),
        sa.CheckConstraint("period_end >= period_start", name="period_order"),
        sa.CheckConstraint("length(currency) = 3", name="currency_length"),
    )
