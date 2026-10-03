"""Retain used refresh hashes and eliminate bearer-only retry credentials."""

import sqlalchemy as sa
from alembic import op

revision = "0009_refresh_reuse_detection"
down_revision = "0008_pause_scheduling"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "used_app_refresh_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("app_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_used_app_refresh_tokens_session_id",
        "used_app_refresh_tokens",
        ["session_id"],
    )
    op.execute(
        "INSERT INTO used_app_refresh_tokens (token_hash, session_id, used_at) SELECT previous_refresh_token_hash, session_id, updated_at FROM app_sessions WHERE previous_refresh_token_hash IS NOT NULL"
    )
    with op.batch_alter_table("app_sessions") as batch:
        batch.drop_column("refresh_token_ciphertext")
        batch.drop_column("previous_refresh_token_hash")
        batch.drop_column("previous_refresh_expires_at")


def downgrade():
    with op.batch_alter_table("app_sessions") as batch:
        batch.add_column(
            sa.Column("refresh_token_ciphertext", sa.String(255), nullable=True)
        )
        batch.add_column(
            sa.Column("previous_refresh_token_hash", sa.String(64), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "previous_refresh_expires_at", sa.DateTime(timezone=True), nullable=True
            )
        )
    op.drop_table("used_app_refresh_tokens")
