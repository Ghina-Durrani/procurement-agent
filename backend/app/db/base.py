"""Shared base for all database models: the declarative base and constraint naming.

Models live in app/models/. Alembic reads Base.metadata to compare the models with
the database and to generate migrations.
"""
import uuid
from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Without naming rules PostgreSQL invents constraint names, and Alembic cannot
# reliably drop or rename them later.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


# JSON for flexible extras; stored as JSONB (indexable) on PostgreSQL.
JsonType = sa.JSON().with_variant(JSONB(), "postgresql")

# Money is an exact decimal (D-023), never a float. 14 digits in total, 2 after the point.
Money = sa.Numeric(14, 2)


def enum_type(enum_cls: type[Enum], name: str) -> sa.Enum:
    """Store an enum as VARCHAR plus a CHECK constraint instead of a native PostgreSQL enum.

    A native enum is hard to change later (ALTER TYPE inside migrations); VARCHAR plus a
    CHECK gives the same protection and is easy to edit.
    """
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


def uuid_pk() -> Mapped[uuid.UUID]:
    # Random UUIDs cannot be guessed, unlike /requests/1, /requests/2, ...
    return mapped_column(primary_key=True, default=uuid.uuid4)


def created_at_col() -> Mapped[datetime]:
    return mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())


def updated_at_col() -> Mapped[datetime]:
    return mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


def same_org_fk(local_column: str, target_table: str, name: str) -> sa.ForeignKeyConstraint:
    """A foreign key that also forces both rows to belong to the same organization.

    It links (organization_id, local_column) to (target.organization_id, target.id), so a
    row of company A can never point at a row of company B, even if application code has
    a bug. The target table needs UNIQUE (organization_id, id).
    """
    return sa.ForeignKeyConstraint(
        ["organization_id", local_column],
        [f"{target_table}.organization_id", f"{target_table}.id"],
        name=name,
    )
