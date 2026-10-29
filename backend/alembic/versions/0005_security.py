"""least-privilege roles, column grants, row-level security

Revision ID: 0005
Revises: 0004
"""
import os

from alembic import op
from sqlalchemy import text

from migration_utils import run_sql_file

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _pw(name: str, default: str) -> str:
    return os.environ.get(name, default).replace("'", "''")   # literal-safe


def upgrade() -> None:
    run_sql_file(
        "006_security.sql",
        APP_RW_PASSWORD=_pw("APP_RW_PASSWORD", "app_rw_dev"),
        APP_RO_PASSWORD=_pw("APP_RO_PASSWORD", "app_ro_dev"),
        ANALYTICS_PASSWORD=_pw("ANALYTICS_PASSWORD", "analytics_dev"),
    )


def downgrade() -> None:
    op.execute(text("DROP POLICY IF EXISTS claim_select ON claim"))
    op.execute(text("DROP POLICY IF EXISTS claim_insert ON claim"))
    op.execute(text("DROP POLICY IF EXISTS audit_staff_select ON audit_log"))
    op.execute(text("ALTER TABLE claim DISABLE ROW LEVEL SECURITY"))
    op.execute(text("ALTER TABLE audit_log DISABLE ROW LEVEL SECURITY"))
    op.execute(text("DROP FUNCTION IF EXISTS set_user_role, app_is_staff, app_user_id CASCADE"))
    # roles are cluster-wide and may own nothing here; leave them in place on purpose
