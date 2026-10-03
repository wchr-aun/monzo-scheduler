"""Add rotatable app refresh sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0007_create_app_sessions"
down_revision = "0006_add_running_transfer_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_sessions",
        sa.Column("session_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=255),
            sa.ForeignKey("monzo_credentials.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("refresh_token_ciphertext", sa.String(length=255), nullable=True),
        sa.Column("previous_refresh_token_hash", sa.String(length=64), nullable=True),
        sa.Column("previous_refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_app_sessions_user_id", "app_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_app_sessions_user_id", table_name="app_sessions")
    op.drop_table("app_sessions")
