"""Cap existing and new sessions at a fixed lifetime from authentication."""

from datetime import timedelta
import sqlalchemy as sa
from alembic import op

revision = "0010_absolute_session_expiry"
down_revision = "0009_refresh_reuse_detection"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "app_sessions",
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    table = sa.table(
        "app_sessions",
        sa.column("session_id", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("absolute_expires_at", sa.DateTime),
    )
    connection = op.get_bind()
    for session_id, created_at in connection.execute(
        sa.select(table.c.session_id, table.c.created_at)
    ).all():
        connection.execute(
            table.update()
            .where(table.c.session_id == session_id)
            .values(absolute_expires_at=created_at + timedelta(days=30))
        )
    with op.batch_alter_table("app_sessions") as batch:
        batch.alter_column(
            "absolute_expires_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )


def downgrade():
    with op.batch_alter_table("app_sessions") as batch:
        batch.drop_column("absolute_expires_at")
