from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from threading import Lock
from uuid import uuid4

import jwt
from cryptography.fernet import Fernet
from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import AppSession, MonzoCredential
from app.schemas.monzo import MonzoTokenResponse

APP_REFRESH_TOKEN_TTL = timedelta(days=60)
APP_REFRESH_RETRY_GRACE = timedelta(seconds=30)
_APP_REFRESH_LOCK = Lock()


@dataclass(frozen=True)
class AppTokenPair:
    access_token: str
    refresh_token: str


def _hash_refresh_token(refresh_token: str) -> str:
    return sha256(refresh_token.encode()).hexdigest()


def _encode_access_token(
    user_id: str, session_version: int, session_id: str, settings: Settings, now: datetime
) -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "ver": session_version,
            "sid": session_id,
            "iat": now,
            "exp": now + timedelta(seconds=settings.jwt_expiration_seconds),
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )


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
) -> AppTokenPair:
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
    return _create_app_session(credential, session, settings, now)


def _create_app_session(
    credential: MonzoCredential,
    session: Session,
    settings: Settings,
    now: datetime,
) -> AppTokenPair:
    session_id = str(uuid4())
    refresh_token = secrets.token_urlsafe(48)
    app_session = AppSession(
        session_id=session_id,
        user_id=credential.user_id,
        session_version=credential.session_version,
        refresh_token_hash=_hash_refresh_token(refresh_token),
        refresh_token_ciphertext=encrypt_token(refresh_token, settings),
        expires_at=now + APP_REFRESH_TOKEN_TTL,
        created_at=now,
        updated_at=now,
    )
    session.add(app_session)
    session.commit()
    return AppTokenPair(
        access_token=_encode_access_token(
            credential.user_id,
            credential.session_version,
            session_id,
            settings,
            now,
        ),
        refresh_token=refresh_token,
    )


def rotate_app_refresh_token(
    refresh_token: str, session_factory, settings: Settings
) -> AppTokenPair | None:
    """Rotate a refresh token, allowing brief retries of concurrent requests."""
    with _APP_REFRESH_LOCK:
        return _rotate_app_refresh_token_locked(refresh_token, session_factory, settings)


def _rotate_app_refresh_token_locked(
    refresh_token: str, session_factory, settings: Settings
) -> AppTokenPair | None:
    now = datetime.now(timezone.utc)
    token_hash = _hash_refresh_token(refresh_token)
    with session_factory() as session:
        app_session = (
            session.query(AppSession)
            .filter(
                or_(
                    AppSession.refresh_token_hash == token_hash,
                    AppSession.previous_refresh_token_hash == token_hash,
                )
            )
            .with_for_update()
            .one_or_none()
        )
        if app_session is None or app_session.revoked_at is not None:
            return None
        if app_session.expires_at.replace(tzinfo=timezone.utc) <= now:
            return None
        credential = session.get(MonzoCredential, app_session.user_id)
        if credential is None or credential.session_version != app_session.session_version:
            return None

        if app_session.previous_refresh_token_hash == token_hash:
            previous_expiry = app_session.previous_refresh_expires_at
            if (
                previous_expiry is None
                or previous_expiry.replace(tzinfo=timezone.utc) <= now
                or app_session.refresh_token_ciphertext is None
            ):
                return None
            current_refresh_token = decrypt_token(
                app_session.refresh_token_ciphertext, settings
            )
            if current_refresh_token is None:
                return None
            return AppTokenPair(
                access_token=_encode_access_token(
                    credential.user_id,
                    credential.session_version,
                    app_session.session_id,
                    settings,
                    now,
                ),
                refresh_token=current_refresh_token,
            )

        next_token = secrets.token_urlsafe(48)
        result = session.execute(
            update(AppSession)
            .execution_options(synchronize_session=False)
            .where(
                AppSession.session_id == app_session.session_id,
                AppSession.refresh_token_hash == token_hash,
                AppSession.revoked_at.is_(None),
                AppSession.expires_at > now,
            )
            .values(
                refresh_token_hash=_hash_refresh_token(next_token),
                refresh_token_ciphertext=encrypt_token(next_token, settings),
                previous_refresh_token_hash=token_hash,
                previous_refresh_expires_at=now + APP_REFRESH_RETRY_GRACE,
                expires_at=now + APP_REFRESH_TOKEN_TTL,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            session.rollback()
            return None
        session.commit()
        return AppTokenPair(
            access_token=_encode_access_token(
                credential.user_id,
                credential.session_version,
                app_session.session_id,
                settings,
                now,
            ),
            refresh_token=next_token,
        )
