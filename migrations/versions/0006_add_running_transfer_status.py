"""Track scheduled transfers while they are executing."""

from alembic import op

revision = "0006_add_running_transfer_status"
down_revision = "0005_encrypt_monzo_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("scheduled_transfers") as batch:
        batch.drop_constraint("ck_scheduled_transfers_status", type_="check")
        batch.create_check_constraint(
            "ck_scheduled_transfers_status",
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
        )


def downgrade() -> None:
    with op.batch_alter_table("scheduled_transfers") as batch:
        batch.drop_constraint("ck_scheduled_transfers_status", type_="check")
        batch.create_check_constraint(
            "ck_scheduled_transfers_status",
            "status IN ('pending', 'completed', 'failed', 'cancelled')",
        )
