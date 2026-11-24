"""The demo seed creates the demo organization and employee once and reuses them after."""
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Organization, User
from app.services.intake.seed_demo import DEMO_ORGANIZATION, seed
from tests.db.db_factories import make_org, make_user

pytestmark = pytest.mark.integration


def test_seed_is_safe_to_run_twice(session: Session) -> None:
    first = seed(session, "Demo.Employee@Example.test")
    second = seed(session, "demo.employee@example.test")
    assert first.id == second.id
    assert first.email == "demo.employee@example.test"
    orgs = session.scalar(
        select(func.count()).select_from(Organization).where(Organization.name == DEMO_ORGANIZATION)
    )
    assert orgs == 1


def test_seed_refuses_an_email_from_another_organization(session: Session) -> None:
    taken = make_user(session, make_org(session))
    with pytest.raises(SystemExit):
        seed(session, taken.email)
    assert session.get_one(User, taken.id).organization_id != session.scalar(
        select(Organization.id).where(Organization.name == DEMO_ORGANIZATION)
    )
