"""Application JWT validation and Monzo access-token resolution."""

from datetime import datetime, timedelta, timezone

import httpx
import jwt
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db.models import MonzoCredential
from app.observability import get_logger, monzo_error_details
from app.services.monzo import refresh_access_token

logger = get_logger(__name__)


class SessionAuthenticationError(Exception):
    """The application session token is missing or invalid."""


class MonzoConnectionError(Exception):
    """The user does not have usable Monzo credentials."""


class TokenStorageError(Exception):
    """Stored Monzo credentials could not be read or updated."""


class MonzoTokenResponseError(Exception):
    """Monzo returned an unusable token response."""


def decode_user_id(token: str, settings: Settings, session_factory) -> str:
    if not settings.jwt_secret_key:
        raise TokenStorageError("Session signing is not configured")

    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "ver"]},
        )
    except jwt.InvalidTokenError as exc:
        raise SessionAuthenticationError from exc

    user_id = claims["sub"]
    if not isinstance(user_id, str) or not user_id:
        raise SessionAuthenticationError
    try:
        with session_factory() as session:
            credential = session.get(MonzoCredential, user_id)
            if credential is not None and claims["ver"] != credential.session_version:
                raise SessionAuthenticationError
    except SQLAlchemyError as exc:
        raise TokenStorageError("Token storage is unavailable") from None
    return user_id


async def resolve_monzo_access_token(user_id: str, session_factory, settings: Settings) -> str:
    try:
        with session_factory() as session:
            credential = session.get(MonzoCredential, user_id)
            if credential is None:
                raise MonzoConnectionError
            access_token = credential.access_token
            refresh_token = credential.refresh_token
            expires_at = credential.expires_at
    except SQLAlchemyError as exc:
        raise TokenStorageError("Token storage is unavailable") from None

    if _as_utc(expires_at) > datetime.now(timezone.utc):
        return access_token
    if not refresh_token:
        raise MonzoConnectionError
    if not settings.monzo_client_id or not settings.monzo_client_secret:
        raise TokenStorageError("Monzo OAuth is not configured")

    try:
        refreshed = await refresh_access_token(refresh_token, settings)
    except httpx.HTTPStatusError as exc:
        error_code, error_message = monzo_error_details(exc.response)
        logger.warning(
            "monzo_token_refresh_exception upstream_status=%d "
            "monzo_code=%r monzo_message=%r",
            exc.response.status_code,
            error_code,
            error_message,
        )
        if exc.response.status_code in {400, 401, 403}:
            raise MonzoConnectionError from exc
        raise
    except (ValidationError, ValueError) as exc:
        raise MonzoTokenResponseError from exc

    if refreshed.user_id != user_id:
        raise MonzoTokenResponseError

    now = datetime.now(timezone.utc)
    try:
        with session_factory() as session:
            credential = session.get(MonzoCredential, user_id)
            if credential is None:
                raise MonzoConnectionError
            credential.access_token = refreshed.access_token
            credential.refresh_token = refreshed.refresh_token or refresh_token
            credential.token_type = refreshed.token_type
            credential.expires_at = now + timedelta(seconds=refreshed.expires_in)
            credential.updated_at = now
            session.commit()
    except SQLAlchemyError as exc:
        raise TokenStorageError("Token storage is unavailable") from None

    return refreshed.access_token


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
