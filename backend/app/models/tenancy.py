"""Who uses the system: organizations (the tenants) and their users."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(sa.String(200), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class User(Base):
    """A person. No password column yet: the authentication design is open (D-011, Q-004)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id"), index=True
    )
    email: Mapped[str] = mapped_column(sa.String(320), unique=True)
    full_name: Mapped[str] = mapped_column(sa.String(200))
    # Plain text such as "Manager". It must equal a role name used in the organization's
    # PolicyConfig, because the policy engine returns role names as text.
    role: Mapped[str] = mapped_column(sa.String(50))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        # Lets other tables use "same organization" foreign keys (see same_org_fk).
        sa.UniqueConstraint("organization_id", "id", name="uq_users_org_id_id"),
        sa.CheckConstraint("email = lower(email)", name="email_lowercase"),
        sa.CheckConstraint("length(trim(role)) > 0", name="role_not_blank"),
    )
