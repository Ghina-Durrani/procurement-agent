"""Create the demo company for local development (D-058, D-059).

Run from backend/:  python -m app.services.intake.seed_demo
It creates, once, and reuses after:
- the demo organization and the demo employee (email from DEMO_USER_EMAIL);
- the active policy settings: the demo values the experiment uses (evaluation/cases/context.json,
  POLICY_RULES.md section 6), with this organization's id;
- the demo supplier list (approved and blocked) from the same file;
- one budget for the current year.
Synthetic data only. Refuses to run outside development.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_session_factory
from app.models import Budget, Organization, PolicyConfig, Supplier, User
from app.models.enums import SupplierStatus

DEMO_ORGANIZATION = "Demo Company (synthetic)"
DEMO_ROLE = "Requester"
DEMO_BUDGET = "Demo annual budget"
DEMO_BUDGET_TOTAL = Decimal("5000000")


def seed(db: Session, email: str, today: date | None = None) -> User:
    email = email.strip().lower()
    org = db.scalars(select(Organization).where(Organization.name == DEMO_ORGANIZATION)).one_or_none()
    if org is None:
        org = Organization(name=DEMO_ORGANIZATION)
        db.add(org)
        db.flush()
    user = db.scalars(select(User).where(User.email == email)).one_or_none()
    if user is None:
        user = User(organization_id=org.id, email=email, full_name="Demo Employee", role=DEMO_ROLE)
        db.add(user)
        db.flush()
    elif user.organization_id != org.id:
        raise SystemExit(f"{email} already belongs to another organization; choose another email.")
    _seed_company_data(db, org, user, today or date.today())
    db.commit()
    return user


def _seed_company_data(db: Session, org: Organization, creator: User, today: date) -> None:
    # Read-only use of the experiment's demo context, so the app and System B share settings.
    from app.services.evaluation.context import load_context

    context = load_context()
    has_config = db.scalars(
        select(PolicyConfig.id).where(PolicyConfig.organization_id == org.id)
    ).first()
    if has_config is None:
        config = context.policy_config.model_copy(update={"organization_id": org.id})
        db.add(
            PolicyConfig(
                organization_id=org.id,
                policy_version=config.policy_version,
                config=config.model_dump(mode="json"),
                is_active=True,
                created_by_user_id=creator.id,
            )
        )
    existing = set(db.scalars(select(Supplier.name).where(Supplier.organization_id == org.id)))
    for names, status in (
        (context.suppliers.approved, SupplierStatus.APPROVED),
        (context.suppliers.blocked, SupplierStatus.BLOCKED),
    ):
        for name in names:
            if name not in existing:
                db.add(Supplier(organization_id=org.id, name=name, status=status))
    has_budget = db.scalars(
        select(Budget.id).where(Budget.organization_id == org.id, Budget.name == DEMO_BUDGET)
    ).first()
    if has_budget is None:
        db.add(
            Budget(
                organization_id=org.id,
                name=DEMO_BUDGET,
                period_start=date(today.year, 1, 1),
                period_end=date(today.year, 12, 31),
                total_amount=DEMO_BUDGET_TOTAL,
                currency="PKR",
            )
        )


def main() -> int:
    settings = get_settings()
    if settings.app_env != "development":
        print("Refused: the demo seed runs only when APP_ENV=development.")
        return 1
    if not settings.demo_user_email:
        print("Set DEMO_USER_EMAIL in .env first (for example demo.employee@example.test).")
        return 1
    with get_session_factory()() as db:
        user = seed(db, settings.demo_user_email)
    print(f"Demo company ready: {user.email} ({DEMO_ORGANIZATION}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
