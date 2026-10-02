import logging
import secrets
from time import monotonic
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.observability import monzo_error_details
from app.schemas.monzo import MonzoTokenResponse
from app.services.monzo import exchange_authorization_code
from app.services.token_store import save_monzo_tokens

router = APIRouter(tags=["monzo"])
logger = logging.getLogger("schedzo.oauth")
OAUTH_STATE_TTL_SECONDS = 600
MAX_PENDING_OAUTH_STATES = 1000


@router.get("/monzo-redirect")
def monzo_redirect(request: Request):
    settings = request.app.state.settings
    if not settings.monzo_client_id:
        logger.error("oauth_redirect_failed reason=oauth_not_configured")
        raise HTTPException(status_code=503, detail="Monzo OAuth is not configured")

    now = monotonic()
    states = request.app.state.oauth_states
    for old_state, created_at in tuple(states.items()):
        if now - created_at > OAUTH_STATE_TTL_SECONDS:
            states.pop(old_state, None)
    if len(states) >= MAX_PENDING_OAUTH_STATES:
        raise HTTPException(status_code=429, detail="Too many pending OAuth attempts")
    state = secrets.token_urlsafe(32)
    states[state] = now
    url = httpx.URL(
        "https://auth.monzo.com/",
        params={
            "client_id": settings.monzo_client_id,
            "redirect_uri": settings.monzo_redirect_uri,
            "response_type": "code",
            "state": state,
        },
    )
    response = RedirectResponse(str(url), status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        "monzo_oauth_state",
        state,
        httponly=True,
        secure=urlparse(settings.monzo_redirect_uri).scheme == "https",
        samesite="lax",
        path="/monzo-callback",
        max_age=600,
    )
    return response


@router.get("/monzo-callback")
async def monzo_callback(request: Request, code: str, state: str):
    states = request.app.state.oauth_states
    created_at = states.get(state)
    if created_at is None or monotonic() - created_at > OAUTH_STATE_TTL_SECONDS or not secrets.compare_digest(
        state, request.cookies.get("monzo_oauth_state", "")
    ):
        logger.warning("oauth_callback_failed reason=invalid_state")
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    states.pop(state, None)

    settings = request.app.state.settings
    if not settings.monzo_client_id or not settings.monzo_client_secret:
        logger.error("oauth_callback_failed reason=oauth_not_configured")
        raise HTTPException(status_code=503, detail="Monzo OAuth is not configured")
    if not settings.jwt_secret_key:
        logger.error("oauth_callback_failed reason=session_signing_not_configured")
        raise HTTPException(status_code=503, detail="Session signing is not configured")
    try:
        token_response = MonzoTokenResponse.model_validate(
            await exchange_authorization_code(code, settings)
        )
    except httpx.HTTPStatusError as exc:
        error_code, error_message = monzo_error_details(exc.response)
        logger.warning(
            "oauth_token_exchange_failed upstream_status=%d "
            "monzo_code=%r monzo_message=%r",
            exc.response.status_code,
            error_code,
            error_message,
        )
        raise HTTPException(
            status_code=exc.response.status_code, detail="Monzo token exchange failed"
        ) from exc
    except httpx.RequestError as exc:
        logger.error(
            "oauth_token_exchange_failed reason=monzo_unreachable",
        )
        raise HTTPException(status_code=503, detail="Monzo API is unreachable") from exc
    except (ValidationError, ValueError) as exc:
        logger.error("oauth_token_exchange_failed reason=invalid_response")
        raise HTTPException(status_code=502, detail="Monzo returned an invalid token response") from exc

    try:
        with request.app.state.session_factory() as session:
            session_token = save_monzo_tokens(token_response, session, settings)
    except SQLAlchemyError as exc:
        logger.error("oauth_callback_failed reason=token_storage_unavailable")
        raise HTTPException(status_code=503, detail="Token storage is unavailable") from exc

    response = JSONResponse(
        {
            "token": session_token,
            "expiresIn": settings.jwt_expiration_seconds,
        }
    )
    response.delete_cookie("monzo_oauth_state", path="/monzo-callback")
    return response
