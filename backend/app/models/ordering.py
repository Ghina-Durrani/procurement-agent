"""Purchase orders."""
import uuid
from datetime import datetime
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
from app.models.enums import PurchaseOrderStatus


class PurchaseOrder(Base):
    """An order placed with one supplier for the chosen quotation.

    The database makes three things impossible, whatever the application code does:
    1. A PO that disagrees with its quotation on request, supplier, amount or currency.
    2. A PO above the amount a person approved (approved_amount on the request).
    3. More than one live PO for the same request.
    """

    __tablename__ = "purchase_orders"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column()
    quotation_id: Mapped[uuid.UUID] = mapped_column()
    supplier_id: Mapped[uuid.UUID] = mapped_column()
    po_number: Mapped[str] = mapped_column(sa.String(50))
    total_amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(sa.String(3))
    # A copy of procurement_requests.approved_amount at the time of ordering. The foreign
    # key below forces it to equal the request's real value.
    approved_amount: Mapped[Decimal] = mapped_column(Money)
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        enum_type(PurchaseOrderStatus, "purchase_order_status"),
        default=PurchaseOrderStatus.DRAFT,
    )
    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    issued_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        same_org_fk("issued_by_user_id", "users", "fk_purchase_orders_issuer_same_org"),
        # (1) The PO must match its quotation exactly.
        sa.ForeignKeyConstraint(
            [
                "organization_id",
                "quotation_id",
                "request_id",
                "supplier_id",
                "total_amount",
                "currency",
            ],
            [
                "quotations.organization_id",
                "quotations.id",
                "quotations.request_id",
                "quotations.supplier_id",
                "quotations.total_amount",
                "quotations.currency",
            ],
            name="fk_po_matches_quotation",
        ),
        # (2a) The stored ceiling must equal the request's real approved amount.
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id", "approved_amount"],
            [
                "procurement_requests.organization_id",
                "procurement_requests.id",
                "procurement_requests.approved_amount",
            ],
            name="fk_po_ceiling_matches_request",
        ),
        # (2b) ... and the PO may not go above it.
        sa.CheckConstraint("total_amount <= approved_amount", name="within_approved_amount"),
        sa.CheckConstraint("total_amount >= 0", name="total_non_negative"),
        sa.CheckConstraint("length(currency) = 3", name="currency_length"),
        sa.CheckConstraint("length(trim(po_number)) > 0", name="po_number_not_blank"),
        sa.CheckConstraint(
            "status <> 'ISSUED' OR (issued_by_user_id IS NOT NULL AND issued_at IS NOT NULL)",
            name="issued_has_issuer",
        ),
        sa.UniqueConstraint("organization_id", "po_number", name="uq_purchase_orders_org_number"),
        # (3) At most one live (not cancelled) PO per request.
        sa.Index(
            "uq_purchase_orders_one_live_per_request",
            "request_id",
            unique=True,
            postgresql_where=sa.text("status <> 'CANCELLED'"),
        ),
    )
