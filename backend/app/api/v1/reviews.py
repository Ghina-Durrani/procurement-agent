"""Thin router for the review queue (D-065)."""
import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.models.enums import ApprovalDecision
from app.schemas.reviews import ReviewDecisionIn, ReviewItem, ReviewQueue
from app.services.review.service import decide, queue_for

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("", response_model=ReviewQueue)
def review_queue(db: DbSession, user: CurrentUser) -> ReviewQueue:
    """Pending review items the current user's role may decide."""
    return ReviewQueue(items=[ReviewItem.from_item(item, user) for item in queue_for(db, user)])


@router.post("/{approval_id}/decision", response_model=ReviewQueue)
def decide_review(
    approval_id: uuid.UUID, body: ReviewDecisionIn, db: DbSession, user: CurrentUser
) -> ReviewQueue:
    """Approve or reject one item; returns the updated queue."""
    decide(db, user, approval_id, ApprovalDecision(body.decision), body.comment)
    return review_queue(db, user)
