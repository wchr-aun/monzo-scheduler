"""Encrypt stored Monzo tokens with the configured application key."""

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet

from app.config import Settings

revision = "0005_encrypt_monzo_tokens"
down_revision = "0004_add_session_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    key = Settings.from_environment().token_encryption_key
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is required to migrate stored tokens")
    fernet = Fernet(key.encode())
    with op.batch_alter_table("monzo_credentials") as batch:
        batch.alter_column("access_token", new_column_name="access_token_ciphertext")
        batch.alter_column("refresh_token", new_column_name="refresh_token_ciphertext")
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT user_id, access_token_ciphertext, refresh_token_ciphertext FROM monzo_credentials")
    ).all()
    for user_id, access_token, refresh_token in rows:
        connection.execute(
            sa.text(
                "UPDATE monzo_credentials SET access_token_ciphertext=:access, "
                "refresh_token_ciphertext=:refresh WHERE user_id=:user_id"
            ),
            {
                "access": fernet.encrypt(access_token.encode()).decode(),
                "refresh": fernet.encrypt(refresh_token.encode()).decode()
                if refresh_token is not None
                else None,
                "user_id": user_id,
            },
        )


def downgrade() -> None:
    key = Settings.from_environment().token_encryption_key
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is required to migrate stored tokens")
    fernet = Fernet(key.encode())
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT user_id, access_token_ciphertext, refresh_token_ciphertext FROM monzo_credentials")
    ).all()
    for user_id, access_token, refresh_token in rows:
        connection.execute(
            sa.text(
                "UPDATE monzo_credentials SET access_token_ciphertext=:access, "
                "refresh_token_ciphertext=:refresh WHERE user_id=:user_id"
            ),
            {
                "access": fernet.decrypt(access_token.encode()).decode(),
                "refresh": fernet.decrypt(refresh_token.encode()).decode()
                if refresh_token is not None
                else None,
                "user_id": user_id,
            },
        )
    with op.batch_alter_table("monzo_credentials") as batch:
        batch.alter_column("access_token_ciphertext", new_column_name="access_token")
        batch.alter_column("refresh_token_ciphertext", new_column_name="refresh_token")
