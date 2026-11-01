"""RRF matching functions and claim/match workflow procedures

Revision ID: 0003
Revises: 0002
"""
from alembic import op
from sqlalchemy import text

from migration_utils import run_sql_file

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("003_matching.sql")
    run_sql_file("004_workflow.sql")


def downgrade() -> None:
    op.execute(text(
        "DROP FUNCTION IF EXISTS reject_match, confirm_match, close_item, mark_returned, reject_claim, "
        "approve_claim, start_claim_review, assert_staff, refresh_matches, persist_match, find_matches, rrf_fuse CASCADE"))
