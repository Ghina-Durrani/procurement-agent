"""Contract tests: does the database fit the real policy engine?

They run the real engine (app.policy.evaluate), save its real PolicyResult into
policy_evaluations, read it back and rebuild the same PolicyResult. They also build
PolicyInput from database rows, the way the future service layer will.
"""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from db_factories import (
    make_budget,
    make_org,
    make_quotation,
    make_request,
    make_supplier,
    make_user,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    Budget,
    PolicyConfig,
    PolicyEvaluation,
    ProcurementRequest,
    Quotation,
    Supplier,
)
from app.models.enums import (
    ActorType,
    Checkpoint,
    ExtractionStatus,
    PolicyOutcome,
    Priority,
    RequestStatus,
    SupplierStatus,
)
from app.policy import evaluate
from app.policy.types import BudgetStatus, PolicyResult, RecentRequest
from app.policy.types import PolicyConfig as EngineConfig
from app.services.extraction import REQUEST_COLUMN_FOR_FIELD

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)


def demo_config(org_id: Any) -> dict[str, Any]:
    """The demo settings from POLICY_RULES.md section 6. Demo values only."""
    return {
        "organization_id": str(org_id),
        "policy_version": "demo-v1",
        "accepted_currencies": ["PKR"],
        # Extraction field names (D-044); REQUEST_COLUMN_FOR_FIELD maps them to columns.
        "required_fields": [
            "item_description",
            "quantity",
            "estimated_total",
            "currency",
            "business_justification",
        ],
        "approval_tiers": [
            {"up_to": "50000", "approver_role": None},
            {"up_to": "500000", "approver_role": "Manager"},
            {"up_to": None, "approver_role": "Senior Management"},
        ],
        "quotation_bands": [
            {"up_to": "100000", "min_quotations": 1},
            {"up_to": None, "min_quotations": 3},
        ],
        "split_window_days": 30,
        "split_watched_thresholds": ["50000", "100000", "500000"],
        "split_ignored_statuses": ["REJECTED", "WITHDRAWN"],
        "allowed_categories": [
            "OFFICE_SUPPLIES",
            "IT_HARDWARE",
            "FURNITURE",
            "MAINTENANCE_SERVICES",
            "CLEANING_SUPPLIES",
            "PRINTING",
            "TRAVEL",
        ],
        "controlled_categories": {
            "SOFTWARE": "IT",
            "HAZARDOUS_CHEMICALS": "Health & Safety",
            "VEHICLES": "Senior Management",
        },
        "prohibited_categories": ["WEAPONS", "ALCOHOL", "PERSONAL_ITEMS", "GIFT_CARDS"],
        "procurement_officer_role": "Procurement Officer",
        "finance_approver_role": "Finance",
        "emergency_approver_role": "Senior Management",
    }


@pytest.fixture()
def world(session: Session):
    """One organization with a saved policy version, a requester and a request."""
    org = make_org(session)
    admin = make_user(session, org, "Policy Administrator")
    requester = make_user(session, org, "Requester")
    config_row = PolicyConfig(
        organization_id=org.id,
        policy_version="demo-v1",
        is_active=True,
        config=EngineConfig.model_validate(demo_config(org.id)).model_dump(mode="json"),
        created_by_user_id=admin.id,
    )
    session.add(config_row)
    session.flush()
    return org, requester, config_row, make_request(session, org, requester)


def base_input(org: Any, requester: Any, request: Any, **changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "request_id": request.id,
        "organization_id": org.id,
        "checkpoint": "INTAKE",
        "requester_user_id": requester.id,
        "submitted_at": NOW,
        "extraction_status": "VALID",
        "missing_fields": [],
        "estimated_total": "30000.00",
        "currency": "PKR",
        "item_category": "OFFICE_SUPPLIES",
        "supplier_name": "TechZone",
        "supplier_status": "APPROVED",
        "budget_status": "AVAILABLE",
        "proposed_priority": "NORMAL",
        "recent_requests": [],
    }
    data.update(changes)
    return data


def save_and_reload(
    session: Session,
    org: Any,
    request: Any,
    config_row: Any,
    requested_checkpoint: Checkpoint,
    raw_input: dict[str, Any],
    result: PolicyResult,
) -> PolicyResult:
    """Save a result the way the service layer should, then rebuild it from the database."""
    row = PolicyEvaluation(
        organization_id=org.id,
        request_id=request.id,
        checkpoint=requested_checkpoint,  # what the SERVICE asked for, never result.checkpoint
        outcome=result.outcome,
        triggered_rules=[rule.model_dump(mode="json") for rule in result.triggered_rules],
        required_approver_roles=list(result.required_approver_roles),
        policy_version=result.policy_version,
        policy_config_id=config_row.id,
        input_snapshot=json.loads(json.dumps(raw_input, default=str)),
    )
    session.add(row)
    session.flush()
    session.expire(row)
    session.refresh(row)
    return PolicyResult.model_validate(
        {
            "outcome": row.outcome.value,
            "checkpoint": row.checkpoint.value if result.checkpoint else None,
            "triggered_rules": row.triggered_rules,
            "required_approver_roles": row.required_approver_roles,
            "policy_version": row.policy_version,
        }
    )


CASES = [  # (name, input changes, expected outcome, expected rule IDs)
    ("C01 clean request", {}, "CONTINUE", []),
    ("C04 amount 50,000.01", {"estimated_total": "50000.01"}, "HUMAN_REVIEW", ["POL-002"]),
    ("C08 blocked supplier", {"supplier_status": "BLOCKED"}, "BLOCK", ["POL-005"]),
    ("C09 supplier not approved", {"supplier_status": "NOT_APPROVED"}, "HUMAN_REVIEW", ["POL-005"]),
    ("C13 budget insufficient", {"budget_status": "INSUFFICIENT"}, "BLOCK", ["POL-007"]),
    ("C16 emergency", {"proposed_priority": "EMERGENCY"}, "HUMAN_REVIEW", ["POL-008"]),
    (
        "C17 big, blocked supplier, emergency",
        {
            "estimated_total": "1200000",
            "supplier_status": "BLOCKED",
            "proposed_priority": "EMERGENCY",
        },
        "BLOCK",
        ["POL-002", "POL-005", "POL-008"],
    ),
    ("C19 extraction failed", {"extraction_status": "FAILED"}, "HUMAN_REVIEW", ["POL-900"]),
    ("missing currency", {"currency": None}, "HUMAN_REVIEW", ["POL-900"]),
]


@pytest.mark.parametrize(("name", "changes", "outcome", "rule_ids"), CASES,
                         ids=[case[0] for case in CASES])
def test_an_engine_result_survives_a_round_trip_through_the_database(
    session: Session, world, name: str, changes: dict, outcome: str, rule_ids: list[str]
) -> None:
    org, requester, config_row, request = world
    raw = base_input(org, requester, request, **changes)
    result = evaluate(raw, config_row.config)
    assert result.outcome.value == outcome  # the engine itself behaves as documented
    assert result.triggered_rule_ids == rule_ids
    rebuilt = save_and_reload(session, org, request, config_row, Checkpoint.INTAKE, raw, result)
    assert rebuilt == result  # nothing lost or changed by the database


def test_a_self_approval_block_is_saved_at_the_approval_checkpoint(
    session: Session, world
) -> None:
    org, requester, config_row, request = world
    raw = base_input(
        org, requester, request, checkpoint="APPROVAL", acting_user_id=requester.id
    )
    result = evaluate(raw, config_row.config)
    assert result.triggered_rule_ids == ["POL-009"] and result.outcome is PolicyOutcome.BLOCK
    rebuilt = save_and_reload(session, org, request, config_row, Checkpoint.APPROVAL, raw, result)
    assert rebuilt == result


def test_a_fail_closed_result_with_no_checkpoint_can_still_be_saved(
    session: Session, world
) -> None:
    """Broken input gives PolicyResult.checkpoint = None. The audit row must still be saved."""
    org, _, config_row, request = world
    result = evaluate({"garbage": True}, config_row.config)
    assert result.checkpoint is None and result.triggered_rule_ids == ["POL-900"]
    rebuilt = save_and_reload(
        session, org, request, config_row, Checkpoint.INTAKE, {"garbage": True}, result
    )
    assert rebuilt == result


def test_settings_of_another_organization_fail_closed(session: Session, world) -> None:
    org, requester, _, request = world
    other_config = demo_config(make_org(session).id)
    result = evaluate(base_input(org, requester, request), other_config)
    assert result.triggered_rule_ids == ["POL-900"]
    assert result.outcome is PolicyOutcome.HUMAN_REVIEW


def test_a_stored_policy_version_loads_back_into_the_engine(session: Session, world) -> None:
    org, _, config_row, _ = world
    session.expire(config_row)
    session.refresh(config_row)
    loaded = EngineConfig.model_validate(config_row.config)  # exactly what the service will do
    assert loaded.organization_id == org.id
    assert loaded.policy_version == config_row.policy_version
    assert loaded.approval_tiers[1].up_to == Decimal("500000")  # money stayed exact


def test_required_field_names_are_real_request_columns(world) -> None:
    """POL-001 compares names in missing_fields with config.required_fields as plain text.

    Those names are the extraction field names (the extractor writes missing_fields), and
    each one maps to a real column through REQUEST_COLUMN_FOR_FIELD.
    """
    _, _, config_row, _ = world
    columns = {column.name for column in ProcurementRequest.__table__.columns}
    required = config_row.config["required_fields"]
    assert set(required) <= set(REQUEST_COLUMN_FOR_FIELD)
    assert {REQUEST_COLUMN_FOR_FIELD[name] for name in required} <= columns


def test_every_engine_enum_value_is_accepted_by_the_database(session: Session) -> None:
    org = make_org(session)
    user = make_user(session, org)
    for status in ExtractionStatus:
        for priority in Priority:
            make_request(
                session, org, user, extraction_status=status, proposed_priority=priority
            )  # flush raises if any engine value is rejected


def test_an_audit_event_can_carry_the_policy_version_and_rule_ids(
    session: Session, world
) -> None:
    org, requester, config_row, request = world
    result = evaluate(
        base_input(org, requester, request, supplier_status="BLOCKED"), config_row.config
    )
    event = AuditEvent(
        organization_id=org.id,
        actor_type=ActorType.SYSTEM,
        action="POLICY_EVALUATED",
        entity_type="procurement_request",
        entity_id=request.id,
        policy_version=result.policy_version,
        rule_ids=result.triggered_rule_ids,
        reason=result.triggered_rules[0].reason,
    )
    session.add(event)
    session.flush()
    session.expire(event)
    session.refresh(event)
    assert event.rule_ids == ["POL-005"] and event.policy_version == "demo-v1"


# ---- build PolicyInput from database rows, as the service layer will ---------
def recent_from_database(session: Session, org: Any, requester: Any, current_id: Any) -> list:
    rows = (
        session.query(ProcurementRequest)
        .filter(
            ProcurementRequest.organization_id == org.id,
            ProcurementRequest.requester_id == requester.id,
            ProcurementRequest.id != current_id,
            ProcurementRequest.submitted_at >= NOW - timedelta(days=30),
        )
        .all()
    )
    return [
        RecentRequest(
            request_id=row.id,
            submitted_at=row.submitted_at,
            estimated_total=row.estimated_amount,
            currency=row.currency,
            status=row.status.value,
            supplier_name=row.supplier_name,
            item_category=row.category,
        ).model_dump(mode="json")
        for row in rows
    ]


@pytest.mark.parametrize(
    ("days_ago", "status", "expected"),
    [
        (20, RequestStatus.APPROVED, ["POL-004"]),  # C06: inside the 30 days, counts
        (45, RequestStatus.APPROVED, []),  # C07: too old, ignored
        (20, RequestStatus.REJECTED, []),  # rejected requests are ignored
        (20, RequestStatus.WITHDRAWN, []),  # withdrawn requests are ignored
    ],
)
def test_a_split_purchase_is_detected_from_real_database_rows(
    session: Session, world, days_ago: int, status: RequestStatus, expected: list[str]
) -> None:
    org, requester, config_row, request = world
    make_request(
        session,
        org,
        requester,
        supplier_name="TechZone",
        category="OFFICE_SUPPLIES",
        estimated_amount=Decimal("35000.00"),
        currency="PKR",
        status=status,
        submitted_at=NOW - timedelta(days=days_ago),
    )
    raw = base_input(
        org,
        requester,
        request,
        estimated_total="40000.00",
        recent_requests=recent_from_database(session, org, requester, request.id),
    )
    assert evaluate(raw, config_row.config).triggered_rule_ids == expected


# ---- the new tables feed the engine's inputs ----------------------------------
def supplier_status_from_database(session: Session, org: Any, name: str) -> str | None:
    """Look a supplier up by name ignoring case, as the service layer should."""
    supplier = (
        session.query(Supplier)
        .filter(Supplier.organization_id == org.id, func.lower(Supplier.name) == name.lower())
        .one_or_none()
    )
    return supplier.status.value if supplier else None


@pytest.mark.parametrize(
    ("lookup_name", "stored_status", "expected_outcome", "expected_rules"),
    [
        ("techzone", SupplierStatus.APPROVED, "CONTINUE", []),  # case does not matter
        ("TechZone", SupplierStatus.NOT_APPROVED, "HUMAN_REVIEW", ["POL-005"]),
        ("TechZone", SupplierStatus.BLOCKED, "BLOCK", ["POL-005"]),
    ],
)
def test_supplier_status_read_from_the_database_drives_pol_005(
    session: Session, world, lookup_name, stored_status, expected_outcome, expected_rules
) -> None:
    org, requester, config_row, request = world
    make_supplier(session, org, name="TechZone", status=stored_status)
    status = supplier_status_from_database(session, org, lookup_name)
    raw = base_input(org, requester, request, supplier_name=lookup_name, supplier_status=status)
    result = evaluate(raw, config_row.config)
    assert result.outcome.value == expected_outcome
    assert result.triggered_rule_ids == expected_rules


def test_an_unknown_supplier_is_sent_to_review(session: Session, world) -> None:
    org, requester, config_row, request = world
    status = supplier_status_from_database(session, org, "Nobody Ltd")
    assert status is None  # not in the database
    raw = base_input(org, requester, request, supplier_name="Nobody Ltd", supplier_status=status)
    assert evaluate(raw, config_row.config).triggered_rule_ids == ["POL-005"]


def test_the_quotation_count_from_the_database_drives_pol_003(session: Session, world) -> None:
    """300,000 PKR needs 3 quotations (POL-003). One per supplier, so a count is enough.

    At PRE_PO the engine reads the SELECTED quotation's amount and the amount already
    approved for the request (D-039), both taken from the database here.
    """
    org, requester, config_row, request = world
    request.approved_amount = Decimal("300000.00")  # approved by a Manager at intake
    suppliers = [make_supplier(session, org) for _ in range(3)]

    def check_pre_po() -> list[str]:
        count = session.scalar(
            select(func.count(Quotation.id)).where(Quotation.request_id == request.id)
        )
        selected_total = session.scalar(
            select(Quotation.total_amount).where(
                Quotation.request_id == request.id, Quotation.is_selected
            )
        )
        raw = base_input(
            org,
            requester,
            request,
            checkpoint="PRE_PO",
            selected_quotation_total=str(selected_total),
            approved_total=str(request.approved_amount),
            supplier_name="Chosen Supplier",
            supplier_status="APPROVED",
            quotation_count=count,
        )
        return evaluate(raw, config_row.config).triggered_rule_ids

    make_quotation(
        session, org, request, suppliers[0], total_amount=Decimal("300000.00"), is_selected=True
    )
    assert check_pre_po() == ["POL-003"]  # 1 quotation, 3 needed
    make_quotation(session, org, request, suppliers[1])
    make_quotation(session, org, request, suppliers[2])
    assert check_pre_po() == []  # 3 quotations


def budget_status_for(budget: Budget, amount: Decimal) -> BudgetStatus:
    """What the finance check is expected to do with a budgets row (an illustration)."""
    if amount > budget.total_amount - budget.committed_amount:
        return BudgetStatus.INSUFFICIENT
    threshold = budget.finance_review_above
    if threshold is not None and amount > threshold:
        return BudgetStatus.NEEDS_FINANCE_APPROVAL
    return BudgetStatus.AVAILABLE


@pytest.mark.parametrize(
    ("amount", "expected_outcome", "expected_rules"),
    [
        ("30000.00", "CONTINUE", []),
        ("60000.00", "HUMAN_REVIEW", ["POL-002", "POL-007"]),  # Manager tier + finance review
        ("900000.00", "BLOCK", ["POL-002", "POL-007"]),  # more than the 800,000 left
    ],
)
def test_budget_columns_are_enough_to_produce_every_budget_status(
    session: Session, world, amount: str, expected_outcome: str, expected_rules: list[str]
) -> None:
    org, requester, config_row, request = world
    budget = make_budget(
        session,
        org,
        total_amount=Decimal("1000000.00"),
        committed_amount=Decimal("200000.00"),
        finance_review_above=Decimal("50000.00"),
    )
    status = budget_status_for(budget, Decimal(amount))
    raw = base_input(
        org, requester, request, estimated_total=amount, budget_status=status.value
    )
    result = evaluate(raw, config_row.config)
    assert result.outcome.value == expected_outcome
    assert result.triggered_rule_ids == expected_rules
