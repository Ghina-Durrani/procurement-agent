"""Supplier sourcing, RFQs, quotation documents, quotations and supplier evaluation."""
import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    JsonType,
    Money,
    created_at_col,
    enum_type,
    same_org_fk,
    updated_at_col,
    uuid_pk,
)
from app.models.enums import ExtractionStatus, QuotationSource, RfqRecipientStatus, RfqStatus


class Rfq(Base):
    """A request for quotation, generated for one procurement request.

    Actually sending it is outside the current scope, so SENT only records that a person
    marked it as sent.
    """

    __tablename__ = "rfqs"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column()
    status: Mapped[RfqStatus] = mapped_column(
        enum_type(RfqStatus, "rfq_status"), default=RfqStatus.DRAFT
    )
    subject: Mapped[str] = mapped_column(sa.String(200))
    body: Mapped[str] = mapped_column(sa.Text)
    response_due_date: Mapped[date | None]
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        same_org_fk("request_id", "procurement_requests", "fk_rfqs_request_same_org"),
        sa.UniqueConstraint("organization_id", "id", name="uq_rfqs_org_id_id"),
        # An RFQ that is SENT or CLOSED must record when it was sent.
        sa.CheckConstraint(
            "status IN ('DRAFT', 'CANCELLED') OR sent_at IS NOT NULL", name="sent_has_time"
        ),
        sa.Index("ix_rfqs_request", "request_id"),
    )


class RfqSupplier(Base):
    """Which suppliers an RFQ goes to, and whether they answered."""

    __tablename__ = "rfq_suppliers"

    rfq_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("organizations.id"))
    response_status: Mapped[RfqRecipientStatus] = mapped_column(
        enum_type(RfqRecipientStatus, "rfq_recipient_status"), default=RfqRecipientStatus.INVITED
    )
    invited_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        same_org_fk("rfq_id", "rfqs", "fk_rfq_suppliers_rfq_same_org"),
        same_org_fk("supplier_id", "suppliers", "fk_rfq_suppliers_supplier_same_org"),
    )


class Document(Base):
    """An uploaded file, for example a supplier quotation. Immutable.

    Only metadata lives here. The file itself is stored elsewhere under storage_key, an
    opaque name chosen by the server. original_filename is for display only and must never
    be used to build a file path (path traversal).
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column()
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    original_filename: Mapped[str] = mapped_column(sa.String(255))
    content_type: Mapped[str] = mapped_column(sa.String(100))
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger)
    sha256: Mapped[str] = mapped_column(sa.String(64))
    storage_key: Mapped[str] = mapped_column(sa.String(255), unique=True)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        same_org_fk("request_id", "procurement_requests", "fk_documents_request_same_org"),
        same_org_fk("uploaded_by_user_id", "users", "fk_documents_uploader_same_org"),
        sa.UniqueConstraint("organization_id", "id", name="uq_documents_org_id_id"),
        # A hard backstop of 10 MB. The configurable upload limit is enforced at the API.
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="size_in_range"),
        sa.CheckConstraint("length(sha256) = 64", name="sha256_length"),
        sa.Index("ix_documents_request", "request_id"),
    )


class Quotation(Base):
    """A supplier's offer for a request, typed in by a person or read from a document."""

    __tablename__ = "quotations"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column()
    supplier_id: Mapped[uuid.UUID] = mapped_column()
    rfq_id: Mapped[uuid.UUID | None] = mapped_column()
    document_id: Mapped[uuid.UUID | None] = mapped_column()
    total_amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(sa.String(3))  # no default: be explicit
    delivery_days: Mapped[int | None]
    payment_terms: Mapped[str | None] = mapped_column(sa.String(200))
    valid_until: Mapped[date | None]
    source: Mapped[QuotationSource] = mapped_column(
        enum_type(QuotationSource, "quotation_source"), default=QuotationSource.MANUAL_ENTRY
    )
    # Only for EXTRACTED quotations: did the model's output pass validation (D-035)?
    extraction_status: Mapped[ExtractionStatus | None] = mapped_column(
        enum_type(ExtractionStatus, "extraction_status")
    )
    extracted_data: Mapped[dict | None] = mapped_column(JsonType)
    source_evidence: Mapped[dict | None] = mapped_column(JsonType)
    # A person must check this quotation before it can be chosen.
    needs_verification: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    is_selected: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        same_org_fk("request_id", "procurement_requests", "fk_quotations_request_same_org"),
        same_org_fk("supplier_id", "suppliers", "fk_quotations_supplier_same_org"),
        same_org_fk("rfq_id", "rfqs", "fk_quotations_rfq_same_org"),
        same_org_fk("document_id", "documents", "fk_quotations_document_same_org"),
        sa.UniqueConstraint("organization_id", "id", name="uq_quotations_org_id_id"),
        # One quotation per supplier per request, so POL-003 counts distinct suppliers.
        sa.UniqueConstraint("request_id", "supplier_id", name="uq_quotations_request_supplier"),
        # Target for the purchase order's "must match its quotation exactly" foreign key.
        sa.UniqueConstraint(
            "organization_id",
            "id",
            "request_id",
            "supplier_id",
            "total_amount",
            "currency",
            name="uq_quotations_po_match",
        ),
        sa.CheckConstraint("total_amount >= 0", name="total_non_negative"),
        sa.CheckConstraint("delivery_days IS NULL OR delivery_days >= 0", name="delivery_valid"),
        sa.CheckConstraint("length(currency) = 3", name="currency_length"),
        # A quotation read from a document must record whether the reading was valid.
        sa.CheckConstraint(
            "source = 'MANUAL_ENTRY' OR extraction_status IS NOT NULL",
            name="extracted_has_status",
        ),
        # An uncertain extraction can never be the chosen quotation.
        sa.CheckConstraint(
            "NOT is_selected OR (NOT needs_verification "
            "AND (extraction_status IS NULL OR extraction_status = 'VALID'))",
            name="selected_is_verified",
        ),
        # At most ONE selected quotation per request.
        sa.Index(
            "uq_quotations_one_selected_per_request",
            "request_id",
            unique=True,
            postgresql_where=sa.text("is_selected"),
        ),
        sa.Index("ix_quotations_request", "request_id"),
    )


class QuotationItem(Base):
    """One line of a quotation."""

    __tablename__ = "quotation_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column()
    line_number: Mapped[int]
    description: Mapped[str] = mapped_column(sa.Text)
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Money)
    line_total: Mapped[Decimal] = mapped_column(Money)

    __table_args__ = (
        same_org_fk("quotation_id", "quotations", "fk_quotation_items_quotation_same_org"),
        sa.UniqueConstraint("quotation_id", "line_number", name="uq_quotation_items_line"),
        sa.CheckConstraint("line_number >= 1", name="line_positive"),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        # The database re-does the arithmetic, so a wrong extracted total cannot be saved.
        sa.CheckConstraint("line_total = quantity * unit_price", name="line_total_correct"),
        sa.Index("ix_quotation_items_quotation", "quotation_id"),
    )


class SupplierEvaluation(Base):
    """How one quotation scored against the others. Rows are only ever added."""

    __tablename__ = "supplier_evaluations"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column()
    quotation_id: Mapped[uuid.UUID] = mapped_column()
    rank: Mapped[int]
    total_score: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2))
    criteria_scores: Mapped[dict] = mapped_column(JsonType)  # for example price, delivery
    rationale: Mapped[str] = mapped_column(sa.Text)
    method_version: Mapped[str] = mapped_column(sa.String(50))  # which scoring rules were used
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        same_org_fk("request_id", "procurement_requests", "fk_evaluations_request_same_org_sup"),
        same_org_fk("quotation_id", "quotations", "fk_supplier_evaluations_quotation_same_org"),
        sa.CheckConstraint("rank >= 1", name="rank_positive"),
        sa.CheckConstraint("total_score >= 0 AND total_score <= 100", name="score_in_range"),
        sa.Index("ix_supplier_evaluations_request", "request_id", "created_at"),
    )
