"""Turn an ExtractionResult into the PolicyInput the policy engine expects.

Only facts that came from the request go through here. Facts that must come from trusted
company data (is the supplier approved? is there budget? how many quotations?) are passed in
by the caller, never taken from the model. That is the line between "the LLM reads" and
"the code decides".
"""
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from app.policy import (
    BudgetStatus,
    Checkpoint,
    PolicyConfig,
    PolicyInput,
    Priority,
    RecentRequest,
    SupplierStatus,
)

from .schemas import ExtractionResult, FieldStatus


def known_categories(config: PolicyConfig) -> list[str]:
    """Every category code the model may pick: allowed, controlled and prohibited ones.

    Prohibited codes are included on purpose, so a request for a prohibited item is
    recognised and BLOCKED, instead of coming back as "unknown".
    """
    return [
        *config.allowed_categories,
        *config.controlled_categories,
        *config.prohibited_categories,
    ]


def to_policy_input(
    result: ExtractionResult,
    *,
    request_id: UUID,
    organization_id: UUID,
    submitted_at: datetime,
    requester_user_id: UUID | None = None,
    checkpoint: Checkpoint = Checkpoint.INTAKE,
    supplier_status: SupplierStatus | None = None,
    budget_status: BudgetStatus | None = None,
    proposed_priority: Priority | None = None,
    recent_requests: Sequence[RecentRequest] = (),
) -> PolicyInput:
    return PolicyInput(
        request_id=request_id,
        organization_id=organization_id,
        checkpoint=checkpoint,
        requester_user_id=requester_user_id,
        submitted_at=submitted_at,
        extraction_status=result.status,
        missing_fields=list(result.missing_fields),
        estimated_total=result.estimated_total,
        currency=result.currency,
        item_category=result.item_category,
        supplier_name=result.supplier_name,
        supplier_status=supplier_status,
        supplier_conflict=result.field_status("supplier_name") is FieldStatus.CONFLICTING,
        budget_status=budget_status,
        proposed_priority=proposed_priority,
        recent_requests=list(recent_requests),
    )
