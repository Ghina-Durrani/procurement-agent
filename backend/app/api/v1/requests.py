"""Thin router for procurement requests: parse, call the service, return the schema."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, IntakeAI
from app.models import ProcurementRequest
from app.schemas.requests import (
    ApprovalRead,
    ClarificationAnswer,
    RequestCreate,
    RequestDetail,
    RequestList,
    RequestSummary,
)
from app.services.intake.clarification import answer_clarification, rounds_of
from app.services.review.service import approvals_of
from app.services.intake.service import (
    get_own_request,
    latest_evaluations,
    latest_extraction,
    list_own_requests,
    submit_request,
)

router = APIRouter(prefix="/requests", tags=["requests"])


def _detail(db: DbSession, user: CurrentUser, request: ProcurementRequest) -> RequestDetail:
    evaluation = latest_evaluations(db, user, [request.id]).get(request.id)
    return RequestDetail.from_records(
        request,
        latest_extraction(db, request),
        evaluation,
        rounds_of(db, request),
        [ApprovalRead.from_row(a, d) for a, d in approvals_of(db, request)],
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RequestDetail)
def create_request(
    body: RequestCreate, db: DbSession, user: CurrentUser, ai: IntakeAI
) -> RequestDetail:
    return _detail(db, user, submit_request(db, user, body.message, ai))


@router.get("", response_model=RequestList)
def list_requests(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RequestList:
    items, total = list_own_requests(db, user, limit, offset)
    evaluations = latest_evaluations(db, user, [item.id for item in items])
    return RequestList(
        items=[RequestSummary.from_rows(item, evaluations.get(item.id)) for item in items],
        total=total,
    )


@router.get("/{request_id}", response_model=RequestDetail)
def read_request(request_id: uuid.UUID, db: DbSession, user: CurrentUser) -> RequestDetail:
    return _detail(db, user, get_own_request(db, user, request_id))


@router.post("/{request_id}/clarifications", response_model=RequestDetail)
def answer_request_clarification(
    request_id: uuid.UUID,
    body: ClarificationAnswer,
    db: DbSession,
    user: CurrentUser,
    ai: IntakeAI,
) -> RequestDetail:
    """The requester answers the open questions; the request is processed again (D-064)."""
    return _detail(db, user, answer_clarification(db, user, request_id, body.answer, ai))
