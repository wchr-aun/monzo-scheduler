from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import MonzoCredential
from app.schemas.monzo import MonzoTokenResponse


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

    credential.access_token = token_response.access_token
    credential.refresh_token = token_response.refresh_token
    credential.token_type = token_response.token_type
    credential.expires_at = now + timedelta(seconds=token_response.expires_in)
    credential.updated_at = now
    session.commit()

    return jwt.encode(
        {
            "sub": token_response.user_id,
            "iat": now,
            "exp": now + timedelta(seconds=settings.jwt_expiration_seconds),
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )
