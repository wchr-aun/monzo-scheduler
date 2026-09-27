"""Monzo OAuth client operations."""

import httpx

from app.config import Settings
from app.schemas.monzo import MonzoTokenResponse

TOKEN_URL = "https://api.monzo.com/oauth2/token"


async def exchange_authorization_code(code: str, settings: Settings) -> MonzoTokenResponse:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.monzo_client_id,
                "client_secret": settings.monzo_client_secret,
                "redirect_uri": settings.monzo_redirect_uri,
                "code": code,
            },
        )
        response.raise_for_status()
        return MonzoTokenResponse.model_validate(response.json())
