"""Create scheduled transfer setup storage."""

import sqlalchemy as sa
from alembic import op

revision = "0002_create_scheduled_transfers"
down_revision = "0001_create_monzo_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_transfer_setups",
        sa.Column("setup_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hour", sa.SmallInteger(), nullable=False),
        sa.Column("minute", sa.SmallInteger(), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("pot_id", sa.String(length=255), nullable=False),
        sa.Column("account_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_scheduled_transfer_setups_amount"),
        sa.CheckConstraint(
            "hour BETWEEN 0 AND 23", name="ck_scheduled_transfer_setups_hour"
        ),
        sa.CheckConstraint(
            "interval IN ('daily', 'weekly', 'monthly')",
            name="ck_scheduled_transfer_setups_interval",
        ),
        sa.CheckConstraint(
            "minute BETWEEN 0 AND 59",
            name="ck_scheduled_transfer_setups_minute",
        ),
        sa.CheckConstraint(
            "type IN ('withdraw', 'deposit')",
            name="ck_scheduled_transfer_setups_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'deactivated')",
            name="ck_scheduled_transfer_setups_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["monzo_credentials.user_id"]),
        sa.PrimaryKeyConstraint("setup_id"),
    )
    op.create_index(
        op.f("ix_scheduled_transfer_setups_user_id"),
        "scheduled_transfer_setups",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_scheduled_transfer_setups_user_id"),
        table_name="scheduled_transfer_setups",
    )
    op.drop_table("scheduled_transfer_setups")
