"""Browser-bound signed OAuth attempts with persistent single-use consumption."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import secrets
from time import time

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.db.models import ConsumedOAuthState

OAUTH_STATE_TTL_SECONDS = 600


def _signature(payload: str, settings) -> str:
    return hmac.new(
        settings.jwt_secret_key.encode(),
        b"schedzo-oauth-state\x00" + payload.encode(),
        sha256,
    ).hexdigest()


def create_oauth_state(settings, *, now=None):
    payload = f"{int(time() if now is None else now)}.{secrets.token_urlsafe(32)}"
    return f"{payload}.{_signature(payload, settings)}"


def consume_oauth_state(state, cookie, settings, session_factory, *, now=None):
    current = time() if now is None else now
    if (
        not cookie
        or len(state) > 128
        or not hmac.compare_digest(state.encode(), cookie.encode())
    ):
        return False
    try:
        issued, nonce, signature = state.split(".")
        age = current - int(issued)
    except ValueError, TypeError:
        return False
    if not 0 <= age < OAUTH_STATE_TTL_SECONDS or not hmac.compare_digest(
        signature.encode(), _signature(f"{issued}.{nonce}", settings).encode()
    ):
        return False
    current_datetime = datetime.fromtimestamp(current, timezone.utc)
    with session_factory() as session:
        session.execute(
            delete(ConsumedOAuthState).where(
                ConsumedOAuthState.expires_at <= current_datetime
            )
        )
        session.add(
            ConsumedOAuthState(
                state_hash=sha256(state.encode()).hexdigest(),
                expires_at=current_datetime
                + timedelta(seconds=OAUTH_STATE_TTL_SECONDS),
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return False
    return True
