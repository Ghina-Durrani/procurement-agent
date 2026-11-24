"""Request intake: save a new request, process it, and read an employee's own requests.

Every query is scoped by the current user's organization and, for now, by the requester:
an employee sees only their own requests. Reviewers get their own queries when the review
workflow is built. A request that does not belong to the caller is reported as not found.
"""
import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import AuditEvent, Extraction, PolicyEvaluation, ProcurementRequest, User
from app.models.enums import ActorType, RequestStatus

from .llm import IntakeLLM
from .processing import process_request


def submit_request(db: Session, user: User, message: str, llm: IntakeLLM) -> ProcurementRequest:
    """Save the original text first (its own transaction), then process it.

    The request is committed before the AI is called, so the original is never lost even if
    processing fails; processing then saves a fail-closed decision instead.
    """
    request = ProcurementRequest(
        organization_id=user.organization_id,
        requester_id=user.id,
        raw_message=message,
        status=RequestStatus.RECEIVED,
    )
    db.add(request)
    db.flush()  # gives the request its id for the audit event
    db.add(
        AuditEvent(
            organization_id=user.organization_id,
            actor_type=ActorType.USER,
            actor_user_id=user.id,
            action="REQUEST_RECEIVED",
            entity_type="procurement_request",
            entity_id=request.id,
            # The text itself stays in the request row; the audit log keeps only its size.
            details={"message_chars": len(message)},
        )
    )
    db.commit()
    db.refresh(request)  # loads submitted_at, set by the database
    process_request(db, request, llm)
    db.refresh(request)
    return request


def _own_requests(user: User) -> Select[ProcurementRequest]:
    return select(ProcurementRequest).where(
        ProcurementRequest.organization_id == user.organization_id,
        ProcurementRequest.requester_id == user.id,
    )


def get_own_request(db: Session, user: User, request_id: uuid.UUID) -> ProcurementRequest:
    request = db.scalars(_own_requests(user).where(ProcurementRequest.id == request_id)).one_or_none()
    if request is None:
        raise NotFound("Request not found.")
    return request


def list_own_requests(
    db: Session, user: User, limit: int, offset: int
) -> tuple[list[ProcurementRequest], int]:
    query = _own_requests(user)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(ProcurementRequest.submitted_at.desc(), ProcurementRequest.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), total



def latest_extraction(db: Session, request: ProcurementRequest) -> Extraction | None:
    return db.scalars(
        select(Extraction)
        .where(
            Extraction.organization_id == request.organization_id,
            Extraction.request_id == request.id,
        )
        .order_by(Extraction.attempt_number.desc())
        .limit(1)
    ).one_or_none()


def latest_evaluations(
    db: Session, user: User, request_ids: list[uuid.UUID]
) -> dict[uuid.UUID, PolicyEvaluation]:
    """The newest policy evaluation of each request, in one query."""
    if not request_ids:
        return {}
    rows = db.scalars(
        select(PolicyEvaluation)
        .where(
            PolicyEvaluation.organization_id == user.organization_id,
            PolicyEvaluation.request_id.in_(request_ids),
        )
        .order_by(PolicyEvaluation.created_at, PolicyEvaluation.id)
    ).all()
    return {row.request_id: row for row in rows}  # later rows overwrite earlier ones
