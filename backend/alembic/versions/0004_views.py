"""views and materialized views

Revision ID: 0004
Revises: 0003
"""
from alembic import op
from sqlalchemy import text

from migration_utils import run_sql_file

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("005_views.sql")


def downgrade() -> None:
    op.execute(text("DROP FUNCTION IF EXISTS refresh_analytics CASCADE"))
    op.execute(text(
        "DROP MATERIALIZED VIEW IF EXISTS mv_match_quality, mv_location_hotspots, mv_recovery_stats, mv_status_counts"))
    op.execute(text("DROP VIEW IF EXISTS v_likely_owners, v_claim_queue, v_match_details, v_open_items"))
