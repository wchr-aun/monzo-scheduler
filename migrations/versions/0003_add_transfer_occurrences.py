"""Create scheduled transfer occurrence storage."""

import sqlalchemy as sa
from alembic import op

revision = "0003_add_transfer_occurrences"
down_revision = "0002_create_scheduled_transfers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_transfers",
        sa.Column("transfer_id", sa.String(length=36), nullable=False),
        sa.Column("setup_id", sa.String(length=36), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'cancelled')",
            name="ck_scheduled_transfers_status",
        ),
        sa.ForeignKeyConstraint(["setup_id"], ["scheduled_transfer_setups.setup_id"]),
        sa.PrimaryKeyConstraint("transfer_id"),
    )
    op.create_index(
        "ix_scheduled_transfers_setup_id",
        "scheduled_transfers",
        ["setup_id"],
        unique=False,
    )
    op.create_index(
        "ix_scheduled_transfers_scheduled_for",
        "scheduled_transfers",
        ["scheduled_for"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scheduled_transfers_scheduled_for", table_name="scheduled_transfers"
    )
    op.drop_index("ix_scheduled_transfers_setup_id", table_name="scheduled_transfers")
    op.drop_table("scheduled_transfers")
