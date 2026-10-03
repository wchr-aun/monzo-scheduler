"""Persist emergency-stop state independently of application sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0008_pause_scheduling"
down_revision = "0007_create_app_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "monzo_credentials",
        sa.Column(
            "scheduling_paused", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade():
    op.drop_column("monzo_credentials", "scheduling_paused")
