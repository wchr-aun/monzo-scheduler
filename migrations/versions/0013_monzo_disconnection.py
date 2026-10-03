"""Persist blocked connections and outstanding provider revocations."""

import sqlalchemy as sa
from alembic import op

revision = "0013_monzo_disconnection"
down_revision = "0012_refresh_history_index"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "monzo_credentials",
        sa.Column(
            "disconnected", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "monzo_credentials",
        sa.Column(
            "revocation_pending",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("monzo_credentials", "revocation_pending")
    op.drop_column("monzo_credentials", "disconnected")
