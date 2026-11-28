"""The review queue and review decisions (D-065).

Flow:
1. When a request goes to AWAITING_APPROVAL or NEEDS_VERIFICATION, one PENDING approval is
   opened per role the policy engine asked for (`open_approvals`). If it named none (for
   example the fail-closed POL-900), a Procurement Officer reviews it.
2. A reviewer sees the pending items their role may decide (`queue_for`), in their own
   organization only.
3. A decision (`decide`) is checked on the server every time: same organization, a role that
   may decide it (roles.py), still pending, still the request's current review, and POL-009
   from the policy engine (nobody decides their own request). Rows are locked, so two people
   clicking at once cannot both count.
4. One rejection rejects the request. When every required role has approved, the request is
   approved for its estimated amount.

Approve is refused when the request has no reliable reading (NEEDS_VERIFICATION) or still
lacks required details (POL-001): approving would clear a purchase nobody can describe. The
reviewer rejects with a comment and the employee sends a clear request.
"""
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound
from app.models import Approval, AuditEvent, PolicyEvaluation, ProcurementRequest, User
from app.models.enums import ActorType, ApprovalDecision, RequestStatus
from app.policy import Checkpoint, PolicyInput, PolicyOutcome, evaluate
from app.services.intake import company_facts

from .roles import roles_user_can_decide

# Used when the settings cannot be read: someone must still look at the request.
FALLBACK_REVIEWER_ROLE = "PROCUREMENT_OFFICER"

_UNDER_REVIEW = (RequestStatus.AWAITING_APPROVAL, RequestStatus.NEEDS_VERIFICATION)


def reviewer_roles(
    status: RequestStatus, required_roles: list[str], procurement_role: str
) -> list[str]:
    """Which roles must review a request that a person has to look at."""
    if status is RequestStatus.NEEDS_VERIFICATION:
        return [procurement_role]  # nothing reliable was read: a procurement check, not an amount
    roles = [role.strip().upper() for role in required_roles if role and role.strip()]
    return list(dict.fromkeys(roles)) or [procurement_role]


def open_approvals(
    db: Session, request: ProcurementRequest, evaluation_id: uuid.UUID, roles: list[str]
) -> None:
    for role in roles:
        db.add(
            Approval(
                organization_id=request.organization_id,
                request_id=request.id,
                policy_evaluation_id=evaluation_id,
                required_role=role,
            )
        )


def approve_refusal(request: ProcurementRequest, evaluation: PolicyEvaluation | None) -> str | None:
    """Why Approve is not allowed for this request, or None when it is."""
    if request.status is RequestStatus.NEEDS_VERIFICATION:
        return "The system could not read this request reliably; it can only be rejected."
    rules = {rule.get("rule_id") for rule in (evaluation.triggered_rules if evaluation else [])}
    if "POL-001" in rules:
        return "Required details are still missing; it can only be rejected."
    return None


@dataclass
class QueueItem:
    approval: Approval
    request: ProcurementRequest
    evaluation: PolicyEvaluation
    requester: User


def queue_for(db: Session, user: User) -> list[QueueItem]:
    """Pending items this user may decide, oldest request first, own organization only."""
    policy = company_facts.active_policy(db, user.organization_id)
    allowed = roles_user_can_decide(user.role, policy[0] if policy else None)
    rows = db.execute(
        select(Approval, ProcurementRequest, PolicyEvaluation, User)
        .join(
            ProcurementRequest,
            (ProcurementRequest.id == Approval.request_id)
            & (ProcurementRequest.organization_id == Approval.organization_id),
        )
        .join(PolicyEvaluation, PolicyEvaluation.id == Approval.policy_evaluation_id)
        .join(User, User.id == ProcurementRequest.requester_id)
        .where(
            Approval.organization_id == user.organization_id,
            Approval.decision == ApprovalDecision.PENDING,
            func.upper(Approval.required_role).in_(allowed),
            ProcurementRequest.status.in_(_UNDER_REVIEW),
        )
        .order_by(ProcurementRequest.submitted_at, Approval.required_role)
    ).all()
    items = [QueueItem(*row) for row in rows]
    # Only the request's current review: an older one is replaced when it is evaluated again.
    return [item for item in items if _is_current(db, item.request, item.evaluation)]


def _latest_intake(db: Session, request: ProcurementRequest) -> PolicyEvaluation | None:
    return db.scalars(
        select(PolicyEvaluation)
        .where(
            PolicyEvaluation.organization_id == request.organization_id,
            PolicyEvaluation.request_id == request.id,
            PolicyEvaluation.checkpoint == Checkpoint.INTAKE,
        )
        .order_by(PolicyEvaluation.created_at.desc(), PolicyEvaluation.id.desc())
        .limit(1)
    ).one_or_none()


def _is_current(db: Session, request: ProcurementRequest, evaluation: PolicyEvaluation) -> bool:
    latest = _latest_intake(db, request)
    return latest is not None and latest.id == evaluation.id


def approvals_of(db: Session, request: ProcurementRequest) -> list[tuple[Approval, User | None]]:
    """Every approval of a request with the person who decided it, oldest first."""
    rows = db.execute(
        select(Approval, User)
        .outerjoin(User, User.id == Approval.decided_by_user_id)
        .where(
            Approval.organization_id == request.organization_id,
            Approval.request_id == request.id,
        )
        .order_by(Approval.created_at, Approval.required_role)
    ).all()
    return [(approval, decider) for approval, decider in rows]


def decide(
    db: Session,
    user: User,
    approval_id: uuid.UUID,
    decision: ApprovalDecision,
    comment: str | None,
) -> ProcurementRequest:
    """Record one reviewer's decision after every server-side check."""
    approval = db.scalars(
        select(Approval)
        .where(Approval.id == approval_id, Approval.organization_id == user.organization_id)
        .with_for_update()
    ).one_or_none()
    if approval is None:
        raise NotFound("Review item not found.")
    request = db.scalars(
        select(ProcurementRequest)
        .where(
            ProcurementRequest.id == approval.request_id,
            ProcurementRequest.organization_id == user.organization_id,
        )
        .with_for_update()
    ).one()

    policy = company_facts.active_policy(db, user.organization_id)
    config = policy[0] if policy else None
    if approval.required_role.strip().upper() not in roles_user_can_decide(user.role, config):
        raise Forbidden("Your role cannot decide this item.")
    if approval.decision is not ApprovalDecision.PENDING:
        raise Conflict("This item was already decided.")
    evaluation = _latest_intake(db, request)
    if request.status not in _UNDER_REVIEW or evaluation is None or evaluation.id != approval.policy_evaluation_id:
        raise Conflict("This request is no longer waiting for this review.")
    if decision is ApprovalDecision.APPROVED:
        refusal = approve_refusal(request, evaluation)
        if refusal:
            raise Conflict(refusal)

    # POL-009 from the policy engine, the only place that decides policy. Saved either way.
    check_input = PolicyInput(
        request_id=request.id,
        organization_id=request.organization_id,
        checkpoint=Checkpoint.APPROVAL,
        requester_user_id=request.requester_id,
        acting_user_id=user.id,
        submitted_at=request.submitted_at,
    )
    check = evaluate(check_input, config)
    db.add(
        PolicyEvaluation(
            organization_id=request.organization_id,
            request_id=request.id,
            checkpoint=Checkpoint.APPROVAL,
            outcome=check.outcome,
            triggered_rules=[rule.model_dump(mode="json") for rule in check.triggered_rules],
            required_approver_roles=list(check.required_approver_roles),
            policy_version=check.policy_version,
            policy_config_id=policy[1] if policy else None,
            input_snapshot=check_input.model_dump(mode="json"),
            created_at=func.clock_timestamp(),
        )
    )
    if check.outcome is not PolicyOutcome.CONTINUE:
        _audit(
            db,
            request,
            user,
            "REVIEW_DECISION_REFUSED",
            {"approval_id": str(approval.id), "rules": sorted(set(check.triggered_rule_ids))},
        )
        db.commit()  # the refused attempt stays on record
        reasons = " ".join(rule.reason for rule in check.triggered_rules)
        raise Forbidden(reasons or "This decision is not allowed.")

    now = datetime.now(UTC)
    approval.decision = decision
    approval.decided_by_user_id = user.id
    approval.decided_at = now
    approval.comment = comment
    if decision is ApprovalDecision.APPROVED:
        approval.approved_amount = request.estimated_amount
    db.flush()

    previous = request.status
    if decision is ApprovalDecision.REJECTED:
        request.status = RequestStatus.REJECTED
    else:
        pending = db.scalars(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.organization_id == request.organization_id,
                Approval.policy_evaluation_id == approval.policy_evaluation_id,
                Approval.decision != ApprovalDecision.APPROVED,
            )
        ).one()
        if pending == 0:
            request.status = RequestStatus.APPROVED
            request.approved_amount = request.estimated_amount
    _audit(
        db,
        request,
        user,
        "REVIEW_DECIDED",
        {
            "approval_id": str(approval.id),
            "required_role": approval.required_role,
            "decision": decision.value,
            "from_status": previous.value,
            "to_status": request.status.value,
        },
    )
    db.commit()
    db.refresh(request)
    return request


def _audit(
    db: Session, request: ProcurementRequest, user: User, action: str, details: dict[str, object]
) -> None:
    db.add(
        AuditEvent(
            organization_id=request.organization_id,
            actor_type=ActorType.USER,
            actor_user_id=user.id,
            action=action,
            entity_type="procurement_request",
            entity_id=request.id,
            details=details,
        )
    )
