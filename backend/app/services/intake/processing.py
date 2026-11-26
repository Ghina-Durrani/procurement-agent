"""Run a saved request through the System B pipeline and save every result (slice task 3).

Order, exactly as in the experiment: extraction (one AI call, evidence checked by code) →
priority → company facts from the database → policy engine. The AI never decides. The
decision, its rules and reasons, the extraction and the exact policy input are saved, so any
decision can be explained and replayed. If anything is missing the engine fails closed.
"""
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Extraction, PolicyEvaluation, ProcurementRequest
from app.models.enums import ActorType, RequestStatus
from app.policy import (
    Checkpoint,
    ExtractionStatus,
    PolicyInput,
    PolicyOutcome,
    PolicyResult,
    evaluate,
)
from app.services.extraction import (
    REQUEST_COLUMN_FOR_FIELD,
    ExtractionResult,
    FieldStatus,
    extract_request,
    known_categories,
    names_in_text,
    to_policy_input,
)
from app.services.urgency import propose_priority

from . import company_facts
from .llm import IntakeLLM

log = logging.getLogger(__name__)

# Column sizes in procurement_requests; a longer value stays only in the extraction row.
_COLUMN_LIMITS = {"unit": 30, "currency": 3, "category": 100, "supplier_name": 200}


def status_for(result: PolicyResult, nothing_read: bool) -> RequestStatus:
    """Where the request goes next (D-059). Only CONTINUE moves it forward without a person."""
    rule_ids = set(result.triggered_rule_ids)
    if result.outcome is PolicyOutcome.BLOCK:
        return RequestStatus.BLOCKED
    if result.outcome is PolicyOutcome.CONTINUE:
        return RequestStatus.APPROVED
    if nothing_read:
        # The AI call failed or its answer was unusable. Asking the employee for "missing"
        # details would mislead: they may well have written them. A person checks instead.
        return RequestStatus.NEEDS_VERIFICATION
    if "POL-001" in rule_ids:  # the requester must add details (clarification, later slice)
        return RequestStatus.NEEDS_CLARIFICATION
    return RequestStatus.AWAITING_APPROVAL  # a person must review (review queue, later slice)


def process_request(db: Session, request: ProcurementRequest, llm: IntakeLLM) -> None:
    """Extract, evaluate and save. Never raises for AI or policy problems; they fail closed."""
    try:
        _process(db, request, llm)
    except Exception:  # an unexpected bug or database error: keep the request reviewable
        db.rollback()
        log.exception("Processing failed for request %s", request.id)  # no request text logged
        _save_failed(db, request)


def _process(db: Session, request: ProcurementRequest, llm: IntakeLLM) -> None:
    policy = company_facts.active_policy(db, request.organization_id)
    if policy is None:
        # No valid settings: do not spend an AI call; the engine fails closed (POL-900).
        _save_failed(db, request, reason="no active policy settings")
        return
    config, config_id = policy

    extraction = extract_request(
        request.raw_message,
        llm.client,
        categories=known_categories(config),
        required_fields=config.fields_to_collect(),
        max_chars=len(request.raw_message) + 1,  # the API already enforced the length limit
    )
    submitted_on = request.submitted_at.date()
    proposal = propose_priority(extraction.urgency.level, extraction.delivery_deadline, submitted_on)
    policy_input = to_policy_input(
        extraction,
        request_id=request.id,
        organization_id=request.organization_id,
        submitted_at=request.submitted_at,
        requester_user_id=request.requester_id,
        checkpoint=Checkpoint.INTAKE,
        supplier_status=company_facts.supplier_status(
            db, request.organization_id, extraction.supplier_name
        ),
        budget_status=company_facts.budget_status(
            db, request.organization_id, extraction.estimated_total, extraction.currency, submitted_on
        ),
        proposed_priority=proposal.priority,
        recent_requests=company_facts.recent_requests(db, request, config.split_window_days),
        blocked_suppliers_in_text=names_in_text(
            request.raw_message, company_facts.blocked_supplier_names(db, request.organization_id)
        ),
    )
    result = evaluate(policy_input, config)

    extraction_row = Extraction(
        organization_id=request.organization_id,
        request_id=request.id,
        attempt_number=_next_attempt(db, request),
        extraction_status=extraction.status,
        extracted_data=extraction.model_dump(mode="json"),
        urgency_evidence=[extraction.urgency.evidence] if extraction.urgency.evidence else [],
        ambiguities=list(extraction.ambiguities),
        conflicts=[
            name
            for name, field in extraction.fields.items()
            if field.status is FieldStatus.CONFLICTING
        ],
        source_evidence=extraction.evidence,
        model_name=llm.label,
    )
    db.add(extraction_row)
    _copy_fields(request, extraction)
    request.needed_by_date = proposal.deadline
    request.proposed_priority = proposal.priority
    request.extraction_status = extraction.status
    request.missing_fields = list(extraction.missing_fields)
    nothing_read = _nothing_read(extraction)
    _save_decision(db, request, policy_input, result, config_id, nothing_read=nothing_read)
    _audit(
        db,
        request,
        "EXTRACTION_COMPLETED",
        {"extraction_status": extraction.status.value, "model": llm.label},
    )
    db.commit()


def _save_failed(db: Session, request: ProcurementRequest, reason: str = "processing error") -> None:
    """Record a fail-closed decision without trusting anything from the failed attempt."""
    policy = company_facts.active_policy(db, request.organization_id)
    config, config_id = policy if policy is not None else (None, None)
    policy_input = PolicyInput(
        request_id=request.id,
        organization_id=request.organization_id,
        checkpoint=Checkpoint.INTAKE,
        requester_user_id=request.requester_id,
        submitted_at=request.submitted_at,
        extraction_status=ExtractionStatus.FAILED,
    )
    result = evaluate(policy_input, config)
    request.extraction_status = ExtractionStatus.FAILED
    _save_decision(db, request, policy_input, result, config_id, nothing_read=True, note=reason)
    db.commit()


def _save_decision(
    db: Session,
    request: ProcurementRequest,
    policy_input: PolicyInput,
    result: PolicyResult,
    config_id: Any,
    nothing_read: bool,
    note: str | None = None,
) -> None:
    previous = request.status
    request.status = status_for(result, nothing_read)
    if request.status is RequestStatus.APPROVED:
        # No approval was needed, so policy cleared the requester's own estimate (POL-002).
        request.approved_amount = policy_input.estimated_total
    db.add(
        PolicyEvaluation(
            organization_id=request.organization_id,
            request_id=request.id,
            checkpoint=Checkpoint.INTAKE,
            outcome=result.outcome,
            triggered_rules=[rule.model_dump(mode="json") for rule in result.triggered_rules],
            required_approver_roles=list(result.required_approver_roles),
            policy_version=result.policy_version,
            policy_config_id=config_id,
            input_snapshot=policy_input.model_dump(mode="json"),
        )
    )
    details: dict[str, Any] = {
        "outcome": result.outcome.value,
        "rules": sorted(set(result.triggered_rule_ids)),
        "from_status": previous.value,
        "to_status": request.status.value,
    }
    if note:
        details["note"] = note
    _audit(db, request, "POLICY_EVALUATED", details)


def _nothing_read(extraction: ExtractionResult) -> bool:
    """True when no usable reading came back: the call failed, or every field is missing
    because the answer itself was unusable (problems recorded). An answer that was read
    and simply found nothing has no problems, so the employee is asked instead."""
    if extraction.status is ExtractionStatus.FAILED:
        return True
    all_missing = all(field.status is FieldStatus.MISSING for field in extraction.fields.values())
    return all_missing and bool(extraction.problems)


def _copy_fields(request: ProcurementRequest, extraction: ExtractionResult) -> None:
    """Copy PRESENT values into the request columns; everything else stays None."""
    for field_name, column in REQUEST_COLUMN_FOR_FIELD.items():
        value = extraction.value(field_name)
        limit = _COLUMN_LIMITS.get(column)
        if isinstance(value, str) and limit is not None and len(value) > limit:
            value = None
        setattr(request, column, value)


def _next_attempt(db: Session, request: ProcurementRequest) -> int:
    count = db.scalar(select(func.count()).where(Extraction.request_id == request.id)) or 0
    return count + 1


def _audit(db: Session, request: ProcurementRequest, action: str, details: dict[str, Any]) -> None:
    # The system, not a person, did this step.
    db.add(
        AuditEvent(
            organization_id=request.organization_id,
            actor_type=ActorType.SYSTEM,
            action=action,
            entity_type="procurement_request",
            entity_id=request.id,
            details=details,
        )
    )
