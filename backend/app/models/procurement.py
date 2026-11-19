"""The procurement request and what Module 1 (extraction, clarification) attaches to it."""
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
from app.models.enums import ExtractionStatus, Priority, RequestStatus


class ProcurementRequest(Base):
    __tablename__ = "procurement_requests"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("organizations.id"))
    requester_id: Mapped[uuid.UUID] = mapped_column()
    status: Mapped[RequestStatus] = mapped_column(
        enum_type(RequestStatus, "request_status"), default=RequestStatus.RECEIVED
    )
    # The original text, kept unchanged. It is UNTRUSTED data: never instructions.
    raw_message: Mapped[str] = mapped_column(sa.Text)

    # Filled in later by extraction and clarification, so all are nullable. Whether the
    # request is complete is decided by policy rule POL-001, not by the database.
    item_description: Mapped[str | None] = mapped_column(sa.Text)
    purpose: Mapped[str | None] = mapped_column(sa.Text)  # reason for buying
    category: Mapped[str | None] = mapped_column(sa.String(100))
    # The supplier as named in the request. It may not match any known supplier.
    supplier_name: Mapped[str | None] = mapped_column(sa.String(200))
    quantity: Mapped[int | None]
    unit: Mapped[str | None] = mapped_column(sa.String(30))
    estimated_amount: Mapped[Decimal | None] = mapped_column(Money)
    # No default on purpose. A missing currency must stay visible so the policy engine
    # raises POL-900. A default of PKR would hide the problem.
    currency: Mapped[str | None] = mapped_column(sa.String(3))
    needed_by_date: Mapped[date | None]
    # The budget this request draws from, chosen by the finance check. Optional.
    budget_id: Mapped[uuid.UUID | None] = mapped_column()

    # Proposed by code from urgency evidence (D-028). A proposal only, never an approval.
    proposed_priority: Mapped[Priority | None] = mapped_column(enum_type(Priority, "priority"))
    extraction_status: Mapped[ExtractionStatus | None] = mapped_column(
        enum_type(ExtractionStatus, "extraction_status")
    )
    missing_fields: Mapped[list] = mapped_column(JsonType, default=list)
    clarification_round: Mapped[int] = mapped_column(default=0, server_default="0")

    # The most money a human (or policy, when no approval is needed) allowed for this
    # request. A purchase order can never exceed it (see PurchaseOrder). Set by the service
    # only when the request becomes APPROVED.
    approved_amount: Mapped[Decimal | None] = mapped_column(Money)

    submitted_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        same_org_fk("requester_id", "users", "fk_requests_requester_same_org"),
        same_org_fk("budget_id", "budgets", "fk_requests_budget_same_org"),
        sa.UniqueConstraint("organization_id", "id", name="uq_procurement_requests_org_id_id"),
        # Target for the purchase order's "ceiling must match the request" foreign key.
        sa.UniqueConstraint(
            "organization_id", "id", "approved_amount", name="uq_procurement_requests_ceiling"
        ),
        sa.CheckConstraint(
            "approved_amount IS NULL OR approved_amount >= 0", name="approved_non_negative"
        ),
        sa.CheckConstraint("quantity IS NULL OR quantity > 0", name="quantity_positive"),
        sa.CheckConstraint(
            "estimated_amount IS NULL OR estimated_amount >= 0", name="amount_non_negative"
        ),
        sa.CheckConstraint("clarification_round >= 0", name="clarification_round_valid"),
        sa.CheckConstraint("length(currency) = 3", name="currency_length"),
        # A hard backstop. The configurable limit (Settings.max_message_chars) is
        # enforced at the API boundary.
        sa.CheckConstraint("length(raw_message) <= 10000", name="raw_message_max_length"),
        # Serves the "same requester, last 30 days" lookup for rule POL-004.
        sa.Index(
            "ix_requests_org_requester_submitted",
            "organization_id",
            "requester_id",
            "submitted_at",
        ),
        sa.Index("ix_requests_org_status", "organization_id", "status"),
    )


class Extraction(Base):
    """One extraction attempt. Immutable, so extraction accuracy can be measured later.

    Rows are never updated, so there is no updated_at. The reliability of an attempt is
    extraction_status (D-035), not a confidence score reported by the model.
    """

    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column()
    attempt_number: Mapped[int]
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        enum_type(ExtractionStatus, "extraction_status")
    )
    extracted_data: Mapped[dict] = mapped_column(JsonType)
    # Exact quotes from the request that suggest urgency (D-028).
    urgency_evidence: Mapped[list] = mapped_column(JsonType, default=list)
    ambiguities: Mapped[list] = mapped_column(JsonType, default=list)
    conflicts: Mapped[list] = mapped_column(JsonType, default=list)
    source_evidence: Mapped[dict] = mapped_column(JsonType, default=dict)
    model_name: Mapped[str | None] = mapped_column(sa.String(100))  # provider is open (D-008)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        same_org_fk("request_id", "procurement_requests", "fk_extractions_request_same_org"),
        sa.UniqueConstraint("request_id", "attempt_number", name="uq_extractions_request_attempt"),
        sa.CheckConstraint("attempt_number >= 1", name="attempt_positive"),
        sa.Index("ix_extractions_request", "request_id"),
    )


class Clarification(Base):
    """One round of the clarification loop: what was asked and what the requester answered.

    asked_at and answered_at take the place of created_at and updated_at.
    """

    __tablename__ = "clarifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column()
    # The maximum number of rounds (working value 2) is still open (D-031), so the
    # database only requires a positive number.
    round_number: Mapped[int]
    questions: Mapped[list] = mapped_column(JsonType)
    answer_text: Mapped[str | None] = mapped_column(sa.Text)
    asked_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    answered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (
        same_org_fk("request_id", "procurement_requests", "fk_clarifications_request_same_org"),
        sa.UniqueConstraint("request_id", "round_number", name="uq_clarifications_request_round"),
        sa.CheckConstraint("round_number >= 1", name="round_positive"),
        sa.CheckConstraint(
            "(answer_text IS NULL) = (answered_at IS NULL)", name="answer_and_time_together"
        ),
        sa.Index("ix_clarifications_request", "request_id"),
    )
