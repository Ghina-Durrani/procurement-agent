"""block UPDATE, DELETE and TRUNCATE on audit_events and policy_evaluations

Alembic cannot generate triggers, so this migration is written by hand. It makes the
evidence tables append-only at the database level, in addition to the rule that
application code has no update or delete paths for them.
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APPEND_ONLY_TABLES = ("audit_events", "policy_evaluations")


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION forbid_modification() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_modification();"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION forbid_modification();"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table};")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON {table};")
    op.execute("DROP FUNCTION IF EXISTS forbid_modification();")
