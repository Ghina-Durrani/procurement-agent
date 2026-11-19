"""Schema tests: the database itself must refuse bad data, whatever the code does."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa
from db_factories import config_json, is_rejected, make_org, make_request, make_user
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    Clarification,
    Extraction,
    Organization,
    PolicyConfig,
    PolicyEvaluation,
    ProcurementRequest,
    User,
)
from app.models.enums import ActorType, Checkpoint, ExtractionStatus, PolicyOutcome

pytestmark = pytest.mark.integration


def make_evaluation(session: Session):
    org = make_org(session)
    request = make_request(session, org, make_user(session, org))
    evaluation = PolicyEvaluation(
        organization_id=org.id,
        request_id=request.id,
        checkpoint=Checkpoint.INTAKE,
        outcome=PolicyOutcome.HUMAN_REVIEW,
        triggered_rules=[],
        required_approver_roles=[],
        input_snapshot={},
    )
    session.add(evaluation)
    session.flush()
    return org, request, evaluation


# ---- normal case ------------------------------------------------------------
def test_a_full_valid_chain_can_be_saved(session: Session) -> None:
    org = make_org(session)
    user = make_user(session, org)
    request = make_request(
        session, org, user, quantity=10, estimated_amount=Decimal("250000.50"), currency="PKR"
    )
    session.add(
        Extraction(
            organization_id=org.id,
            request_id=request.id,
            attempt_number=1,
            extraction_status=ExtractionStatus.VALID,
            extracted_data={"quantity": 10},
            urgency_evidence=["needed by Friday"],
        )
    )
    session.add(
        Clarification(
            organization_id=org.id,
            request_id=request.id,
            round_number=1,
            questions=["Which model?"],
            answer_text="Standard model",
            answered_at=datetime.now(timezone.utc),
        )
    )
    session.add(
        AuditEvent(
            organization_id=org.id,
            actor_type=ActorType.USER,
            actor_user_id=user.id,
            action="REQUEST_RECEIVED",
            entity_type="procurement_request",
            entity_id=request.id,
            rule_ids=["POL-002"],
            policy_version="demo-v1",
        )
    )
    session.flush()
    saved = session.get(ProcurementRequest, request.id)
    assert saved is not None and saved.estimated_amount == Decimal("250000.50")


# ---- tenant isolation (security) --------------------------------------------
def test_a_request_cannot_use_a_user_from_another_organization(session: Session) -> None:
    org_a, org_b = make_org(session), make_org(session)
    user_b = make_user(session, org_b)
    wrong = ProcurementRequest(organization_id=org_a.id, requester_id=user_b.id, raw_message="x")
    assert is_rejected(session, wrong)


def test_an_extraction_cannot_point_at_a_request_of_another_organization(
    session: Session,
) -> None:
    org_a, org_b = make_org(session), make_org(session)
    request_b = make_request(session, org_b, make_user(session, org_b))
    wrong = Extraction(
        organization_id=org_a.id,
        request_id=request_b.id,
        attempt_number=1,
        extraction_status=ExtractionStatus.VALID,
        extracted_data={},
    )
    assert is_rejected(session, wrong)


def test_a_clarification_cannot_point_at_a_request_of_another_organization(
    session: Session,
) -> None:
    org_a, org_b = make_org(session), make_org(session)
    request_b = make_request(session, org_b, make_user(session, org_b))
    assert is_rejected(
        session,
        Clarification(
            organization_id=org_a.id, request_id=request_b.id, round_number=1, questions=[]
        ),
    )


# ---- invalid values ---------------------------------------------------------
@pytest.mark.parametrize("quantity", [0, -5])
def test_zero_or_negative_quantity_is_rejected(session: Session, quantity: int) -> None:
    org = make_org(session)
    wrong = ProcurementRequest(
        organization_id=org.id,
        requester_id=make_user(session, org).id,
        raw_message="x",
        quantity=quantity,
    )
    assert is_rejected(session, wrong)


def test_negative_money_is_rejected(session: Session) -> None:
    org = make_org(session)
    wrong = ProcurementRequest(
        organization_id=org.id,
        requester_id=make_user(session, org).id,
        raw_message="x",
        estimated_amount=Decimal("-1.00"),
    )
    assert is_rejected(session, wrong)


def test_an_oversized_message_is_rejected(session: Session) -> None:
    org = make_org(session)
    wrong = ProcurementRequest(
        organization_id=org.id, requester_id=make_user(session, org).id, raw_message="a" * 10001
    )
    assert is_rejected(session, wrong)


def test_an_invented_status_is_rejected_by_the_database(session: Session) -> None:
    org = make_org(session)
    request = make_request(session, org, make_user(session, org))
    with pytest.raises(DBAPIError):
        with session.begin_nested():  # bypasses the Python enum on purpose
            session.execute(
                sa.text("UPDATE procurement_requests SET status = 'HACKED' WHERE id = :id"),
                {"id": request.id},
            )


def test_a_missing_currency_stays_missing_and_is_not_defaulted(session: Session) -> None:
    """Raw SQL that leaves currency out, so a database default would show up."""
    org = make_org(session)
    user = make_user(session, org)
    new_id = uuid.uuid4()
    session.execute(
        sa.text(
            "INSERT INTO procurement_requests "
            "(id, organization_id, requester_id, status, raw_message, missing_fields) "
            "VALUES (:id, :org, :user, 'RECEIVED', 'x', '[]')"
        ),
        {"id": new_id, "org": org.id, "user": user.id},
    )
    currency = session.execute(
        sa.text("SELECT currency FROM procurement_requests WHERE id = :id"), {"id": new_id}
    ).scalar_one()
    assert currency is None  # the policy engine must see this and raise POL-900


def test_duplicate_emails_are_rejected(session: Session) -> None:
    org = make_org(session)
    first = make_user(session, org)
    assert is_rejected(
        session, User(organization_id=org.id, email=first.email, full_name="x", role="Requester")
    )


def test_uppercase_emails_are_rejected(session: Session) -> None:
    org = make_org(session)
    assert is_rejected(
        session,
        User(organization_id=org.id, email="Upper@Example.test", full_name="x", role="Requester"),
    )


def test_a_blank_role_is_rejected(session: Session) -> None:
    org = make_org(session)
    assert is_rejected(
        session, User(organization_id=org.id, email="a@example.test", full_name="x", role="   ")
    )


def test_organization_names_are_unique(session: Session) -> None:
    org = make_org(session)
    assert is_rejected(session, Organization(name=org.name))


# ---- policy versions --------------------------------------------------------
def make_config(org: Organization, admin: User, version: str, *, active: bool, **changes):
    return PolicyConfig(
        organization_id=org.id,
        policy_version=version,
        config=changes.pop("config", config_json(org, version)),
        is_active=active,
        created_by_user_id=admin.id,
    )


def test_only_one_policy_version_can_be_active_per_organization(session: Session) -> None:
    org = make_org(session)
    admin = make_user(session, org, "Policy Administrator")
    session.add(make_config(org, admin, "v1", active=True))
    session.flush()
    assert is_rejected(session, make_config(org, admin, "v2", active=True))


def test_an_inactive_policy_version_can_be_added_next_to_the_active_one(
    session: Session,
) -> None:
    org = make_org(session)
    admin = make_user(session, org, "Policy Administrator")
    session.add(make_config(org, admin, "v1", active=True))
    session.flush()
    assert not is_rejected(session, make_config(org, admin, "v2", active=False))


def test_a_policy_version_name_cannot_be_reused(session: Session) -> None:
    org = make_org(session)
    admin = make_user(session, org, "Policy Administrator")
    session.add(make_config(org, admin, "v1", active=False))
    session.flush()
    assert is_rejected(session, make_config(org, admin, "v1", active=False))


def test_policy_json_must_belong_to_its_own_organization(session: Session) -> None:
    org_a, org_b = make_org(session), make_org(session)
    admin = make_user(session, org_a, "Policy Administrator")
    wrong = make_config(org_a, admin, "v1", active=False, config=config_json(org_b, "v1"))
    assert is_rejected(session, wrong)


def test_policy_json_must_carry_the_same_version_as_its_row(session: Session) -> None:
    org = make_org(session)
    admin = make_user(session, org, "Policy Administrator")
    wrong = make_config(org, admin, "v2", active=False, config=config_json(org, "v1"))
    assert is_rejected(session, wrong)


# ---- clarification loop and extraction attempts -----------------------------
def test_an_answer_and_its_time_must_come_together(session: Session) -> None:
    org = make_org(session)
    request = make_request(session, org, make_user(session, org))
    assert is_rejected(
        session,
        Clarification(
            organization_id=org.id,
            request_id=request.id,
            round_number=1,
            questions=["?"],
            answer_text="an answer without a time",
        ),
    )


def test_the_same_extraction_attempt_number_cannot_be_saved_twice(session: Session) -> None:
    org = make_org(session)
    request = make_request(session, org, make_user(session, org))

    def attempt() -> Extraction:
        return Extraction(
            organization_id=org.id,
            request_id=request.id,
            attempt_number=1,
            extraction_status=ExtractionStatus.VALID,
            extracted_data={},
        )

    session.add(attempt())
    session.flush()
    assert is_rejected(session, attempt())


# ---- audit trail ------------------------------------------------------------
def test_a_user_action_without_a_user_id_is_rejected(session: Session) -> None:
    org = make_org(session)
    wrong = AuditEvent(
        organization_id=org.id, actor_type=ActorType.USER, action="X", entity_type="request"
    )
    assert is_rejected(session, wrong)


@pytest.mark.parametrize("statement", ["UPDATE audit_events SET action = 'EDITED'",
                                       "DELETE FROM audit_events"])
def test_audit_events_cannot_be_changed_or_deleted(session: Session, statement: str) -> None:
    org = make_org(session)
    session.add(
        AuditEvent(
            organization_id=org.id,
            actor_type=ActorType.SYSTEM,
            action="REQUEST_RECEIVED",
            entity_type="procurement_request",
        )
    )
    session.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        with session.begin_nested():
            session.execute(sa.text(statement))


@pytest.mark.parametrize("statement", ["UPDATE policy_evaluations SET outcome = 'CONTINUE'",
                                       "DELETE FROM policy_evaluations"])
def test_policy_evaluations_cannot_be_changed_or_deleted(
    session: Session, statement: str
) -> None:
    make_evaluation(session)
    with pytest.raises(DBAPIError, match="append-only"):
        with session.begin_nested():
            session.execute(sa.text(statement))
