from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import MonzoCredential
from app.schemas.monzo import MonzoTokenResponse


def encrypt_token(value: str | None, settings: Settings) -> str | None:
    if value is None:
        return None
    return Fernet(settings.token_encryption_key.encode()).encrypt(value.encode()).decode()


def decrypt_token(value: str | None, settings: Settings) -> str | None:
    if value is None:
        return None
    return Fernet(settings.token_encryption_key.encode()).decrypt(value.encode()).decode()


def save_monzo_tokens(
    token_response: MonzoTokenResponse, session: Session, settings: Settings
) -> str:
    if not settings.jwt_secret_key:
        raise ValueError("JWT_SECRET_KEY is not configured")

    now = datetime.now(timezone.utc)
    credential = session.get(MonzoCredential, token_response.user_id)
    if credential is None:
        credential = MonzoCredential(user_id=token_response.user_id)
        session.add(credential)

    credential.access_token = encrypt_token(token_response.access_token, settings)
    credential.refresh_token = encrypt_token(token_response.refresh_token, settings)
    credential.token_type = token_response.token_type
    credential.session_version = (credential.session_version or 0) + 1
    credential.expires_at = now + timedelta(seconds=token_response.expires_in)
    credential.updated_at = now
    session.commit()

    return jwt.encode(
        {
            "sub": token_response.user_id,
            "ver": credential.session_version,
            "iat": now,
            "exp": now + timedelta(seconds=settings.jwt_expiration_seconds),
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )
