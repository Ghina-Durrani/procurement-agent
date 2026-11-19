"""Policy settings and the evidence trail: policy versions, evaluations, audit events."""
import uuid
from datetime import datetime
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
from app.models.enums import ActorType, ApprovalDecision, Checkpoint, PolicyOutcome


class PolicyConfig(Base):
    """One VERSION of an organization's policy settings (limits, lists, roles).

    The settings are never edited. A change adds a new version and the old one is kept,
    so any past decision can be explained. Only is_active changes, when a version is
    switched on or off.
    """

    __tablename__ = "policy_configs"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    # The same text as policy_version inside the JSON (PolicyConfig.policy_version).
    policy_version: Mapped[str] = mapped_column(sa.String(50))
    config: Mapped[dict] = mapped_column(JsonType)
    is_active: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    created_by_user_id: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        same_org_fk("created_by_user_id", "users", "fk_policy_configs_creator_same_org"),
        sa.UniqueConstraint("organization_id", "id", name="uq_policy_configs_org_id_id"),
        sa.UniqueConstraint(
            "organization_id", "policy_version", name="uq_policy_configs_org_id_policy_version"
        ),
        sa.CheckConstraint("length(trim(policy_version)) > 0", name="version_not_blank"),
        # The JSON must belong to this organization and carry the same version text.
        sa.CheckConstraint(
            "config->>'organization_id' = organization_id::text "
            "AND config->>'policy_version' = policy_version",
            name="config_matches_row",
        ),
        # At most ONE active version per organization.
        sa.Index(
            "uq_policy_configs_one_active_per_org",
            "organization_id",
            unique=True,
            postgresql_where=sa.text("is_active"),
        ),
    )


class PolicyEvaluation(Base):
    """One saved PolicyResult. Append-only: a database trigger blocks UPDATE and DELETE."""

    __tablename__ = "policy_evaluations"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column()
    # The checkpoint the SERVICE asked for. PolicyResult.checkpoint is None when the input
    # was too broken to read, so never copy that value here.
    checkpoint: Mapped[Checkpoint] = mapped_column(enum_type(Checkpoint, "checkpoint"))
    outcome: Mapped[PolicyOutcome] = mapped_column(enum_type(PolicyOutcome, "policy_outcome"))
    triggered_rules: Mapped[list] = mapped_column(JsonType)
    required_approver_roles: Mapped[list] = mapped_column(JsonType)
    # What the engine reported, and (when known) the exact config row it used.
    policy_version: Mapped[str | None] = mapped_column(sa.String(50))
    policy_config_id: Mapped[uuid.UUID | None] = mapped_column()
    # The exact PolicyInput the engine saw, so the decision can be replayed.
    input_snapshot: Mapped[dict] = mapped_column(JsonType)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        same_org_fk("request_id", "procurement_requests", "fk_evaluations_request_same_org"),
        same_org_fk("policy_config_id", "policy_configs", "fk_evaluations_config_same_org"),
        sa.UniqueConstraint("organization_id", "id", name="uq_policy_evaluations_org_id_id"),
        sa.Index("ix_evaluations_request_created", "request_id", "created_at"),
    )


class Approval(Base):
    """A request for a human decision. Created PENDING, then decided by a person."""

    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column()
    policy_evaluation_id: Mapped[uuid.UUID] = mapped_column()  # the result that asked for it
    # Role name as text from PolicyResult.required_approver_roles, e.g. "Manager".
    required_role: Mapped[str] = mapped_column(sa.String(50))
    decision: Mapped[ApprovalDecision] = mapped_column(
        enum_type(ApprovalDecision, "approval_decision"), default=ApprovalDecision.PENDING
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    approved_amount: Mapped[Decimal | None] = mapped_column(Money)
    comment: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        same_org_fk("request_id", "procurement_requests", "fk_approvals_request_same_org"),
        same_org_fk(
            "policy_evaluation_id", "policy_evaluations", "fk_approvals_evaluation_same_org"
        ),
        same_org_fk("decided_by_user_id", "users", "fk_approvals_decider_same_org"),
        sa.UniqueConstraint(
            "policy_evaluation_id", "required_role", name="uq_approvals_evaluation_role"
        ),
        sa.CheckConstraint("length(trim(required_role)) > 0", name="role_not_blank"),
        sa.CheckConstraint(
            "approved_amount IS NULL OR approved_amount >= 0", name="approved_non_negative"
        ),
        # A decision always has a person and a time; a pending item has neither.
        sa.CheckConstraint(
            "(decision = 'PENDING' AND decided_by_user_id IS NULL AND decided_at IS NULL) OR "
            "(decision <> 'PENDING' AND decided_by_user_id IS NOT NULL AND decided_at IS NOT NULL)",
            name="decision_has_decider",
        ),
        # Only an APPROVED decision can carry an approved amount.
        sa.CheckConstraint(
            "approved_amount IS NULL OR decision = 'APPROVED'", name="amount_only_when_approved"
        ),
        # The review queue: "pending items for my role".
        sa.Index("ix_approvals_queue", "organization_id", "decision", "required_role"),
        sa.Index("ix_approvals_request", "request_id"),
    )


class AuditEvent(Base):
    """Append-only record of who or what did what, and why. UPDATE and DELETE are blocked."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("organizations.id"))
    actor_type: Mapped[ActorType] = mapped_column(enum_type(ActorType, "actor_type"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column()
    action: Mapped[str] = mapped_column(sa.String(100))
    entity_type: Mapped[str] = mapped_column(sa.String(50))
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    # BACKEND_GUIDE: record policy version, rule IDs and reason.
    policy_version: Mapped[str | None] = mapped_column(sa.String(50))
    rule_ids: Mapped[list] = mapped_column(JsonType, default=list)
    reason: Mapped[str | None] = mapped_column(sa.Text)
    details: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        same_org_fk("actor_user_id", "users", "fk_audit_events_actor_same_org"),
        sa.CheckConstraint(
            "actor_type <> 'USER' OR actor_user_id IS NOT NULL", name="user_actor_has_id"
        ),
        sa.Index("ix_audit_org_entity", "organization_id", "entity_type", "entity_id"),
        sa.Index("ix_audit_org_created", "organization_id", "created_at"),
    )
