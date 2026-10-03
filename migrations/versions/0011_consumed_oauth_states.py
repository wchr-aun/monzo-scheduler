"""Persist consumption of stateless signed OAuth attempts."""

import sqlalchemy as sa
from alembic import op

revision = "0011_consumed_oauth_states"
down_revision = "0010_absolute_session_expiry"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "consumed_oauth_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_consumed_oauth_states_expires_at", "consumed_oauth_states", ["expires_at"]
    )


def downgrade():
    op.drop_table("consumed_oauth_states")
