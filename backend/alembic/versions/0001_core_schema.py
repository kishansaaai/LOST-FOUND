"""core schema: enums, tables, constraints, indexes

Revision ID: 0001
Revises:
"""
from alembic import op
from sqlalchemy import text

from migration_utils import run_sql_file

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("001_core_schema.sql")


def downgrade() -> None:
    op.execute(text(
        "DROP TABLE IF EXISTS outbox, audit_log, claim, match_item, match, embedding, item, "
        "location, users CASCADE"
    ))
    op.execute(text(
        "DROP TYPE IF EXISTS claim_result, verification_status, match_status, item_category, "
        "item_status, item_type, user_role CASCADE"
    ))
