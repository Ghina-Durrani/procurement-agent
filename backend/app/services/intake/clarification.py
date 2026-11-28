"""The clarification loop (D-029, D-031, D-064): ask the requester for missing details.

How it works:
1. When the policy engine says required details are missing (POL-001), the system saves a
   clarification round with one question per missing field. The questions come from fixed
   templates in code, never from the AI, so they cannot be wrong, invented or manipulated.
2. The requester answers in free text. The answer is saved as its own record; the original
   request text is never edited (D-041).
3. The original text plus every answer goes through the same pipeline again: one extraction
   call, evidence checks, policy engine. Answers are untrusted text, exactly like the request.
4. At most MAX_ROUNDS rounds. If details are still missing after that, a person reviews the
   request instead (fail closed): the requester is not asked forever.
"""
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.models import AuditEvent, Clarification, ProcurementRequest, User
from app.models.enums import ActorType, RequestStatus

from .llm import IntakeLLM

# D-031 / D-057: at most two rounds, then a person decides.
MAX_ROUNDS = 2

# One answer is short: it fills in a few details. Together with the original message
# (at most max_message_chars) the text sent to the AI stays bounded.
MAX_ANSWER_CHARS = 1000

_QUESTIONS = {
    "item_description": "What exactly do you need to buy?",
    "quantity": "How many do you need?",
    "unit": "What unit is the quantity in (for example pieces, boxes or licences)?",
    "estimated_total": "What is the estimated total cost of the whole request?",
    "currency": "Which currency is the amount in (for example PKR)?",
    "item_category": "What kind of item is this (for example furniture, IT hardware or software)?",
    "supplier_name": "Which supplier do you want to buy from?",
    "delivery_deadline": "By when do you need it?",
    "delivery_location": "Where should it be delivered?",
    "business_justification": "Why is this purchase needed?",
}

_LABELS = {
    "item_description": "the item",
    "quantity": "the quantity",
    "unit": "the unit",
    "estimated_total": "the total amount",
    "currency": "the currency",
    "item_category": "the type of item",
    "supplier_name": "the supplier",
    "delivery_deadline": "the deadline",
    "delivery_location": "the delivery place",
    "business_justification": "the reason for buying",
}


def build_questions(fields: list[str], conflicts: dict[str, str]) -> list[dict[str, str]]:
    """One fixed question per field. A conflicting field asks which value is right.

    The conflict note itself is not shown: it was written from the AI's reading and could
    quote the request; the employee only needs to know which detail to state clearly.
    """
    questions = []
    for field in fields:
        if field in conflicts:
            label = _LABELS.get(field, field.replace("_", " "))
            text = f"Your request gives different values for {label}. Which one is correct?"
        else:
            text = _QUESTIONS.get(field, f"Please give {field.replace('_', ' ')}.")
        questions.append({"field": field, "question": text})
    return questions


def text_for_extraction(original: str, rounds: list[Clarification]) -> str:
    """The original request plus every answered round, in order.

    The questions are included because an answer like "5" means nothing without them. They
    are fixed system text. Everything is still wrapped as untrusted request text by the
    extraction prompt, and the injection checks run on the whole of it.
    """
    parts = [original]
    for round_ in sorted(rounds, key=lambda r: r.round_number):
        if round_.answer_text is None:
            continue
        asked = " ".join(q.get("question", "") for q in round_.questions)
        parts.append(
            f"Follow-up questions (round {round_.round_number}): {asked}\n"
            f"Requester's answer: {round_.answer_text}"
        )
    return "\n\n".join(parts)


def rounds_of(db: Session, request: ProcurementRequest) -> list[Clarification]:
    return list(
        db.scalars(
            select(Clarification)
            .where(
                Clarification.organization_id == request.organization_id,
                Clarification.request_id == request.id,
            )
            .order_by(Clarification.round_number)
        ).all()
    )


def ask(
    db: Session, request: ProcurementRequest, fields: list[str], conflicts: dict[str, str]
) -> None:
    """Open the next round. The caller has already checked that another round is allowed."""
    request.clarification_round += 1
    questions = build_questions(fields, conflicts)
    db.add(
        Clarification(
            organization_id=request.organization_id,
            request_id=request.id,
            round_number=request.clarification_round,
            questions=questions,
        )
    )
    db.add(
        AuditEvent(
            organization_id=request.organization_id,
            actor_type=ActorType.SYSTEM,
            action="CLARIFICATION_ASKED",
            entity_type="procurement_request",
            entity_id=request.id,
            details={"round": request.clarification_round, "fields": fields},
        )
    )


def answer_clarification(
    db: Session, user: User, request_id: uuid.UUID, answer: str, llm: IntakeLLM
) -> ProcurementRequest:
    """Save the requester's answer, then process the request again.

    Only the requester can answer, only while the request waits for an answer, and only the
    open round. The request row is locked, so two answers sent at once cannot both count; the
    lock is released when the session ends (commit, or the request's session closing).
    """
    # Imported here to avoid a circular import (processing imports this module).
    from .processing import process_request

    request = db.scalars(
        select(ProcurementRequest)
        .where(
            ProcurementRequest.id == request_id,
            ProcurementRequest.organization_id == user.organization_id,
            ProcurementRequest.requester_id == user.id,
        )
        .with_for_update()
    ).one_or_none()
    if request is None:
        raise NotFound("Request not found.")
    if request.status is not RequestStatus.NEEDS_CLARIFICATION:
        raise Conflict("This request is not waiting for more details.")

    open_round = db.scalars(
        select(Clarification).where(
            Clarification.organization_id == request.organization_id,
            Clarification.request_id == request.id,
            Clarification.round_number == request.clarification_round,
            Clarification.answer_text.is_(None),
        )
    ).one_or_none()
    if open_round is None:
        # Status says "waiting" but no question is open (for example, data from before this
        # feature). Never guess: a person must look at it.
        raise Conflict("This request has no open question. A reviewer will check it.")

    open_round.answer_text = answer
    open_round.answered_at = datetime.now(UTC)
    details: dict[str, Any] = {"round": open_round.round_number, "answer_chars": len(answer)}
    db.add(
        AuditEvent(
            organization_id=request.organization_id,
            actor_type=ActorType.USER,
            actor_user_id=user.id,
            action="CLARIFICATION_ANSWERED",
            entity_type="procurement_request",
            entity_id=request.id,
            # Only the size: the answer text stays in the clarification row.
            details=details,
        )
    )
    db.commit()  # the answer is kept even if processing fails afterwards
    db.refresh(request)
    process_request(db, request, llm)
    db.refresh(request)
    return request
