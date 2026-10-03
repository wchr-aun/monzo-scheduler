"""Scrub obsolete SQLite pages after the plaintext-token migration."""

from alembic import op

revision = "0014_scrub_sqlite_remnants"
down_revision = "0013_monzo_disconnection"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "sqlite":
        return
    # Alembic runs this with the service stopped. Checkpoint old WAL content
    # before rebuilding, so obsolete copies are not left in journal files.
    with op.get_context().autocommit_block():
        connection = op.get_bind()
        connection.exec_driver_sql("PRAGMA secure_delete=ON")
        checkpoint = connection.exec_driver_sql(
            "PRAGMA wal_checkpoint(TRUNCATE)"
        ).fetchone()
        if checkpoint is not None and checkpoint[0] != 0:
            raise RuntimeError(
                "SQLite checkpoint busy; stop all database users before migration"
            )
        mode = connection.exec_driver_sql("PRAGMA journal_mode=DELETE").scalar()
        if mode.lower() != "delete":
            raise RuntimeError("SQLite journals must be closed before rebuilding")
        connection.exec_driver_sql("VACUUM")


def downgrade():
    pass  # Recovered plaintext and deleted pages must never be restored.
