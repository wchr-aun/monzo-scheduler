"""Expire application refresh sessions after 60 days without activity."""

from datetime import timedelta

import sqlalchemy as sa
from alembic import op

revision = "0016_refresh_inactivity_expiry"
down_revision = "0015_nonexpiring_app_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "app_sessions",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    table = sa.table(
        "app_sessions",
        sa.column("session_id", sa.String),
        sa.column("updated_at", sa.DateTime),
        sa.column("expires_at", sa.DateTime),
    )
    connection = op.get_bind()
    for session_id, updated_at in connection.execute(
        sa.select(table.c.session_id, table.c.updated_at)
    ).all():
        connection.execute(
            table.update()
            .where(table.c.session_id == session_id)
            .values(expires_at=updated_at + timedelta(days=60))
        )
    with op.batch_alter_table("app_sessions") as batch:
        batch.alter_column(
            "expires_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )


def downgrade():
    with op.batch_alter_table("app_sessions") as batch:
        batch.drop_column("expires_at")
