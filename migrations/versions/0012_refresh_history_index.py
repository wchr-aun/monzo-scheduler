"""Bound refresh quota checks using indexed session/time lookups."""

from alembic import op

revision = "0012_refresh_history_index"
down_revision = "0011_consumed_oauth_states"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_used_refresh_session_time",
        "used_app_refresh_tokens",
        ["session_id", "used_at"],
    )


def downgrade():
    op.drop_index("ix_used_refresh_session_time", table_name="used_app_refresh_tokens")
