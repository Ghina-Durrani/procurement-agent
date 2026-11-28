"""Who am I, and (development only) which demo users the switcher may pick (D-058, D-065)."""
from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.errors import NotFound
from app.models import User
from app.schemas.reviews import CurrentUserRead, DemoUsers

router = APIRouter(tags=["users"])


@router.get("/me", response_model=CurrentUserRead)
def me(user: CurrentUser) -> CurrentUserRead:
    return CurrentUserRead(email=user.email, full_name=user.full_name, role=user.role)


@router.get("/dev/users", response_model=DemoUsers)
def demo_users(db: DbSession, user: CurrentUser) -> DemoUsers:
    # get_current_user already refuses outside development; this check keeps it explicit.
    if get_settings().app_env != "development":
        raise NotFound("Not found.")
    rows = db.scalars(
        select(User)
        .where(User.organization_id == user.organization_id, User.is_active)
        .order_by(User.full_name)
    ).all()
    return DemoUsers(
        users=[CurrentUserRead(email=u.email, full_name=u.full_name, role=u.role) for u in rows]
    )
