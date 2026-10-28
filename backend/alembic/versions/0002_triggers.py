"""triggers: item/claim state machines, match integrity, audit, outbox

Revision ID: 0002
Revises: 0001
"""
from alembic import op
from sqlalchemy import text

from migration_utils import run_sql_file

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("002_triggers.sql")


def downgrade() -> None:
    for t, names in {
        "item": ["trg_item_guard", "trg_item_updated_at", "trg_audit_item", "trg_outbox_item"],
        "match": ["trg_match_integrity", "trg_audit_match", "trg_outbox_match"],
        "match_item": ["trg_match_item_integrity"],
        "claim": ["trg_claim_guard", "trg_claim_after_approval", "trg_audit_claim", "trg_outbox_claim"],
        "users": ["trg_audit_users"],
        "embedding": ["trg_outbox_embedding"],
    }.items():
        for n in names:
            op.execute(text(f"DROP TRIGGER IF EXISTS {n} ON {t}"))
    op.execute(text(
        "DROP FUNCTION IF EXISTS set_updated_at, item_guard, check_match_integrity, claim_guard, "
        "claim_after_approval, audit_row, enqueue_outbox, enqueue_outbox_embedding CASCADE"))
