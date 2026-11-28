"""API shapes for procurement requests (the boundary between the frontend and the services).

All text in these responses (the message, extracted values, rule reasons) is data. The
frontend shows it as plain text, never as HTML.
"""
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.config import get_settings
from app.models import Clarification, Extraction, PolicyEvaluation, ProcurementRequest
from app.models.enums import ExtractionStatus, PolicyOutcome, Priority, RequestStatus
from app.services.extraction.schemas import EXTRACTED_FIELDS
from app.services.intake.clarification import MAX_ANSWER_CHARS, MAX_ROUNDS


def _utc(value: datetime) -> str:
    # Handbook §3: ISO-8601 in UTC with "Z", whatever time zone the database session uses.
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class RequestCreate(BaseModel):
    # Unknown fields are refused, so a client cannot send organization_id, status or similar.
    model_config = ConfigDict(extra="forbid")

    message: str = Field(description="The request in the employee's own words. Untrusted text.")

    @field_validator("message")
    @classmethod
    def _check_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Write what you need to buy.")
        limit = get_settings().max_message_chars
        if len(value) > limit:
            raise ValueError(f"The message is too long (maximum {limit} characters).")
        return value  # kept exactly as written; the original is never edited (D-041)


class ClarificationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(description="The requester's answer to the open questions. Untrusted text.")

    @field_validator("answer")
    @classmethod
    def _check_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Write your answer.")
        if len(value) > MAX_ANSWER_CHARS:
            raise ValueError(f"The answer is too long (maximum {MAX_ANSWER_CHARS} characters).")
        return value  # kept exactly as written


class QuestionRead(BaseModel):
    field: str
    question: str  # fixed system text, never written by the AI


class ClarificationRead(BaseModel):
    round_number: int
    questions: list[QuestionRead]
    answer: str | None
    asked_at: datetime
    answered_at: datetime | None

    @field_serializer("asked_at")
    def _asked_at(self, value: datetime) -> str:
        return _utc(value)

    @field_serializer("answered_at")
    def _answered_at(self, value: datetime | None) -> str | None:
        return _utc(value) if value is not None else None

    @classmethod
    def from_row(cls, row: Clarification) -> "ClarificationRead":
        return cls(
            round_number=row.round_number,
            questions=[QuestionRead.model_validate(q) for q in row.questions],
            answer=row.answer_text,
            asked_at=row.asked_at,
            answered_at=row.answered_at,
        )


class RuleRead(BaseModel):
    rule_id: str
    outcome: PolicyOutcome
    reason: str
    required_approver_role: str | None = None


class DecisionRead(BaseModel):
    """The latest policy engine result. Produced by code, never by the AI."""

    outcome: PolicyOutcome
    triggered_rules: list[RuleRead]
    required_approver_roles: list[str]
    policy_version: str | None
    evaluated_at: datetime

    @field_serializer("evaluated_at")
    def _evaluated_at(self, value: datetime) -> str:
        return _utc(value)

    @classmethod
    def from_row(cls, row: PolicyEvaluation) -> "DecisionRead":
        return cls(
            outcome=row.outcome,
            triggered_rules=[RuleRead.model_validate(rule) for rule in row.triggered_rules],
            required_approver_roles=list(row.required_approver_roles),
            policy_version=row.policy_version,
            evaluated_at=row.created_at,
        )


class FieldRead(BaseModel):
    """One field as the AI read it and the evidence check kept it."""

    name: str
    status: str  # PRESENT, MISSING, AMBIGUOUS or CONFLICTING
    value: str | None


class RequestSummary(BaseModel):
    id: uuid.UUID
    status: RequestStatus
    message: str
    submitted_at: datetime
    outcome: PolicyOutcome | None = None
    proposed_priority: Priority | None = None

    @field_serializer("submitted_at")
    def _submitted_at(self, value: datetime) -> str:
        return _utc(value)

    @classmethod
    def from_rows(
        cls, request: ProcurementRequest, evaluation: PolicyEvaluation | None
    ) -> "RequestSummary":
        return cls(
            id=request.id,
            status=request.status,
            message=request.raw_message,
            submitted_at=request.submitted_at,
            outcome=evaluation.outcome if evaluation is not None else None,
            proposed_priority=request.proposed_priority,
        )


class RequestDetail(RequestSummary):
    extraction_status: ExtractionStatus | None = None
    missing_fields: list[str] = []
    fields: list[FieldRead] = []
    # Which AI read the request, so a fake development answer is never taken for a real one.
    read_by: str | None = None
    decision: DecisionRead | None = None
    # Every clarification round, oldest first; the last one is open while status is
    # NEEDS_CLARIFICATION and its answer is null.
    clarifications: list[ClarificationRead] = []
    max_clarification_rounds: int = MAX_ROUNDS

    @classmethod
    def from_records(
        cls,
        request: ProcurementRequest,
        extraction: Extraction | None,
        evaluation: PolicyEvaluation | None,
        clarifications: list[Clarification] | None = None,
    ) -> "RequestDetail":
        summary = RequestSummary.from_rows(request, evaluation)
        return cls(
            **summary.model_dump(),
            extraction_status=request.extraction_status,
            missing_fields=list(request.missing_fields or []),
            fields=_fields(extraction),
            read_by=extraction.model_name if extraction is not None else None,
            decision=DecisionRead.from_row(evaluation) if evaluation is not None else None,
            clarifications=[ClarificationRead.from_row(row) for row in clarifications or []],
        )


def _fields(extraction: Extraction | None) -> list[FieldRead]:
    if extraction is None:
        return []
    stored: dict[str, Any] = extraction.extracted_data.get("fields", {})
    result = []
    for name in EXTRACTED_FIELDS:
        field = stored.get(name) or {}
        status = str(field.get("status", "MISSING"))
        value = field.get("value")
        # Only a PRESENT value is shown as a value; other statuses carry no trusted value.
        shown = str(value) if status == "PRESENT" and value is not None else None
        result.append(FieldRead(name=name, status=status, value=shown))
    return result


class RequestList(BaseModel):
    items: list[RequestSummary]
    total: int
