"""Add revocable application session versions."""

import sqlalchemy as sa
from alembic import op

revision = "0004_add_session_version"
down_revision = "0003_add_transfer_occurrences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monzo_credentials",
        sa.Column("session_version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("monzo_credentials", "session_version")
