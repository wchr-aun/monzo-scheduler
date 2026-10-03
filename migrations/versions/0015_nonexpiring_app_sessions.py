"""Remove time-based expiry from application refresh sessions."""

from datetime import timedelta

import sqlalchemy as sa
from alembic import op

revision = "0015_nonexpiring_app_sessions"
down_revision = "0014_scrub_sqlite_remnants"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve revocation, current hashes, and all consumed-token history.
    with op.batch_alter_table("app_sessions") as batch:
        batch.drop_column("absolute_expires_at")
        batch.drop_column("expires_at")


def downgrade():
    with op.batch_alter_table("app_sessions") as batch:
        batch.add_column(
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
    table = sa.table(
        "app_sessions",
        sa.column("session_id", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("expires_at", sa.DateTime),
        sa.column("absolute_expires_at", sa.DateTime),
    )
    connection = op.get_bind()
    for session_id, created_at in connection.execute(
        sa.select(table.c.session_id, table.c.created_at)
    ).all():
        deadline = created_at + timedelta(days=30)
        connection.execute(
            table.update()
            .where(table.c.session_id == session_id)
            .values(
                absolute_expires_at=deadline,
                expires_at=deadline,
            )
        )
    with op.batch_alter_table("app_sessions") as batch:
        batch.alter_column(
            "expires_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
        batch.alter_column(
            "absolute_expires_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
