"""Monzo OAuth and API client operations."""

import asyncio
from collections.abc import Awaitable

import httpx

from app.config import Settings
from app.schemas.monzo import MonzoTokenResponse

MONZO_API_URL = "https://api.monzo.com"
type BalanceResult = httpx.Response | httpx.RequestError


async def exchange_authorization_code(code: str, settings: Settings) -> MonzoTokenResponse:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{MONZO_API_URL}/oauth2/token",
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


async def refresh_access_token(
    refresh_token: str, settings: Settings
) -> MonzoTokenResponse:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{MONZO_API_URL}/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.monzo_client_id,
                "client_secret": settings.monzo_client_secret,
                "refresh_token": refresh_token,
            },
        )
        response.raise_for_status()
        return MonzoTokenResponse.model_validate(response.json())


async def get_accounts(
    access_token: str, account_type: str | None = None
) -> httpx.Response:
    params = {"account_type": account_type} if account_type is not None else None
    return await _get("/accounts", access_token, params=params)


async def get_balance(access_token: str, account_id: str) -> httpx.Response:
    return await _get("/balance", access_token, params={"account_id": account_id})


async def get_balances(
    access_token: str, account_ids: list[str]
) -> list[BalanceResult]:
    """Fetch balances concurrently without failing the whole batch."""
    balance_requests: list[Awaitable[BalanceResult]] = [
        _get_balance_result(access_token, account_id) for account_id in account_ids
    ]
    results = await asyncio.gather(*balance_requests)
    return list(results)


async def _get_balance_result(
    access_token: str, account_id: str
) -> BalanceResult:
    try:
        return await get_balance(access_token, account_id)
    except httpx.RequestError as exc:
        return exc


async def get_pots(access_token: str, current_account_id: str) -> httpx.Response:
    return await _get(
        "/pots",
        access_token,
        params={"current_account_id": current_account_id},
    )


async def _get(
    path: str, access_token: str, *, params: dict[str, str] | None = None
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=15.0) as client:
        return await client.get(
            f"{MONZO_API_URL}{path}",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
