import logging
from uuid import uuid6

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.observability import monzo_error_details
from app.schemas.monzo import MonzoTokenResponse
from app.services.monzo import exchange_authorization_code
from app.services.token_store import save_monzo_tokens

router = APIRouter(tags=["monzo"])
logger = logging.getLogger("schedzo.oauth")


@router.get("/monzo-redirect")
def monzo_redirect(request: Request):
    settings = request.app.state.settings
    if not settings.monzo_client_id:
        logger.error("oauth_redirect_failed reason=oauth_not_configured")
        raise HTTPException(status_code=503, detail="Monzo OAuth is not configured")

    state = uuid6().hex
    request.app.state.oauth_states.add(state)
    url = httpx.URL(
        "https://auth.monzo.com/",
        params={
            "client_id": settings.monzo_client_id,
            "redirect_uri": settings.monzo_redirect_uri,
            "response_type": "code",
            "state": state,
        },
    )
    return RedirectResponse(str(url), status_code=status.HTTP_302_FOUND)


@router.get("/monzo-callback")
async def monzo_callback(request: Request, code: str, state: str):
    states = request.app.state.oauth_states
    if state not in states:
        logger.warning("oauth_callback_failed reason=invalid_state")
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    states.remove(state)

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

    return {
        "token": session_token,
        "expiresIn": settings.jwt_expiration_seconds,
    }
