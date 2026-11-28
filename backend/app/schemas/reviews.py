"""API shapes for the review queue (D-065). All request text is data, shown as plain text."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.models import User
from app.models.enums import RequestStatus
from app.schemas.requests import RuleRead, _utc
from app.services.review.service import QueueItem, approve_refusal

MAX_COMMENT_CHARS = 1000


class ReviewDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["APPROVED", "REJECTED"]
    comment: str | None = Field(default=None, description="Required when rejecting.")

    @model_validator(mode="after")
    def _check(self) -> "ReviewDecisionIn":
        comment = (self.comment or "").strip()
        if len(self.comment or "") > MAX_COMMENT_CHARS:
            raise ValueError(f"The comment is too long (maximum {MAX_COMMENT_CHARS} characters).")
        if self.decision == "REJECTED" and not comment:
            raise ValueError("Write why the request is rejected.")
        self.comment = comment or None
        return self


class ReviewItem(BaseModel):
    approval_id: uuid.UUID
    required_role: str
    request_id: uuid.UUID
    status: RequestStatus
    message: str
    submitted_at: datetime
    requester_name: str
    item_description: str | None
    quantity: int | None
    estimated_total: str | None  # decimal string (Handbook §3)
    currency: str | None
    supplier_name: str | None
    triggered_rules: list[RuleRead]
    # UX hints only; the server checks everything again when a decision is sent.
    approve_blocked_reason: str | None
    is_own_request: bool

    @field_serializer("submitted_at")
    def _submitted_at(self, value: datetime) -> str:
        return _utc(value)

    @classmethod
    def from_item(cls, item: QueueItem, viewer: User) -> "ReviewItem":
        request = item.request
        return cls(
            approval_id=item.approval.id,
            required_role=item.approval.required_role,
            request_id=request.id,
            status=request.status,
            message=request.raw_message,
            submitted_at=request.submitted_at,
            requester_name=item.requester.full_name,
            item_description=request.item_description,
            quantity=request.quantity,
            estimated_total=str(request.estimated_amount) if request.estimated_amount is not None else None,
            currency=request.currency,
            supplier_name=request.supplier_name,
            triggered_rules=[RuleRead.model_validate(rule) for rule in item.evaluation.triggered_rules],
            approve_blocked_reason=approve_refusal(request, item.evaluation),
            is_own_request=request.requester_id == viewer.id,
        )


class ReviewQueue(BaseModel):
    items: list[ReviewItem]


class CurrentUserRead(BaseModel):
    email: str
    full_name: str
    role: str


class DemoUsers(BaseModel):
    users: list[CurrentUserRead]
