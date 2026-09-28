"""Authenticated pass-through routes for Monzo account resources."""

from collections.abc import Awaitable
from typing import Literal, Never, TypeVar

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError

from app.observability import get_logger, monzo_error_details
from app.schemas.monzo import (
    AccountsResponse,
    AccountsWithBalancesResponse,
    AccountWithBalance,
    BalanceResponse,
    PotsResponse,
)
from app.services.authorization import (
    MonzoConnectionError,
    MonzoTokenResponseError,
    SessionAuthenticationError,
    TokenStorageError,
    decode_user_id,
    resolve_monzo_access_token,
)
from app.services.monzo import (
    BalanceResult,
    get_accounts,
    get_balance,
    get_balances,
    get_pots,
)

router = APIRouter(tags=["monzo"])
bearer_scheme = HTTPBearer(auto_error=False)
logger = get_logger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)
ResponseValueT = TypeVar("ResponseValueT")
MonzoOperation = Literal["accounts", "balance", "pots"]


async def monzo_access_token(
    request: Request,
    authorization: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if authorization is None:
        logger.warning(
            "authentication_failed path=%s reason=bearer_token_missing",
            request.url.path,
        )
        _raise_unauthorized("Bearer token required")

    try:
        user_id = decode_user_id(
            authorization.credentials,
            request.app.state.settings,
        )
        return await resolve_monzo_access_token(
            user_id,
            request.app.state.session_factory,
            request.app.state.settings,
        )
    except SessionAuthenticationError:
        logger.warning(
            "authentication_failed path=%s reason=invalid_or_expired_jwt",
            request.url.path,
        )
        _raise_unauthorized("Invalid or expired bearer token")
    except MonzoConnectionError:
        logger.warning(
            "authentication_failed path=%s reason=monzo_connection_unavailable",
            request.url.path,
        )
        _raise_unauthorized("Monzo connection is missing or expired")
    except TokenStorageError as exc:
        logger.error(
            "credential_resolution_failed path=%s reason=storage_or_configuration",
            request.url.path,
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MonzoTokenResponseError as exc:
        logger.error(
            "credential_refresh_failed path=%s reason=invalid_response",
            request.url.path,
        )
        raise HTTPException(
            status_code=502,
            detail="Monzo returned an invalid token response",
        ) from exc
    except httpx.RequestError as exc:
        logger.error(
            "credential_refresh_failed path=%s reason=monzo_unreachable",
            request.url.path,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail="Monzo API is unreachable") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Monzo token refresh failed") from exc


@router.get("/accounts", response_model=AccountsResponse)
async def accounts(
    account_type: str | None = None,
    access_token: str = Depends(monzo_access_token),
) -> AccountsResponse | Response:
    return await _validate_response(
        get_accounts(access_token, account_type),
        AccountsResponse,
        operation="accounts",
    )


@router.get(
    "/accounts-with-balances",
    response_model=AccountsWithBalancesResponse,
)
async def accounts_with_balances(
    account_type: str | None = None,
    access_token: str = Depends(monzo_access_token),
) -> AccountsWithBalancesResponse | Response:
    accounts_response = await _validate_response(
        get_accounts(access_token, account_type),
        AccountsResponse,
        operation="accounts",
    )
    if isinstance(accounts_response, Response):
        return accounts_response

    balance_responses = await get_balances(
        access_token,
        [account.id for account in accounts_response.accounts],
    )
    accounts_with_balances: list[AccountWithBalance] = []
    for account, balance_response in zip(
        accounts_response.accounts, balance_responses, strict=True
    ):
        balance = _optional_balance(balance_response)
        accounts_with_balances.append(
            AccountWithBalance(
                **account.model_dump(),
                balance_details=balance,
            )
        )

    return AccountsWithBalancesResponse(accounts=accounts_with_balances)


def _optional_balance(response: BalanceResult) -> BalanceResponse | None:
    if isinstance(response, httpx.RequestError):
        logger.error(
            "monzo_request_failed operation=balance reason=monzo_unreachable",
            exc_info=(type(response), response, response.__traceback__),
        )
        return None

    try:
        balance = _validate_completed_response(
            response,
            BalanceResponse,
            operation="balance",
        )
    except HTTPException:
        return None

    return balance if isinstance(balance, BalanceResponse) else None


@router.get("/balance", response_model=BalanceResponse)
async def balance(
    account_id: str,
    access_token: str = Depends(monzo_access_token),
) -> BalanceResponse | Response:
    return await _validate_response(
        get_balance(access_token, account_id),
        BalanceResponse,
        operation="balance",
    )


@router.get("/pots", response_model=PotsResponse)
async def pots(
    current_account_id: str,
    access_token: str = Depends(monzo_access_token),
) -> PotsResponse | Response:
    return await _validate_response(
        get_pots(access_token, current_account_id),
        PotsResponse,
        operation="pots",
    )


async def _validate_response(
    response_awaitable: Awaitable[httpx.Response],
    schema: type[SchemaT],
    *,
    operation: MonzoOperation,
) -> SchemaT | Response:
    response = await _await_monzo_response(response_awaitable, operation=operation)
    return _validate_completed_response(response, schema, operation=operation)


async def _await_monzo_response(
    response_awaitable: Awaitable[ResponseValueT],
    *,
    operation: MonzoOperation,
) -> ResponseValueT:
    try:
        return await response_awaitable
    except httpx.RequestError as exc:
        logger.error(
            "monzo_request_failed operation=%s reason=monzo_unreachable",
            operation,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail="Monzo API is unreachable") from exc


def _validate_completed_response(
    response: httpx.Response,
    schema: type[SchemaT],
    *,
    operation: MonzoOperation,
) -> SchemaT | Response:
    if response.is_error:
        error_code, error_message = monzo_error_details(response)
        logger.warning(
            "monzo_request_failed operation=%s upstream_status=%d "
            "monzo_code=%r monzo_message=%r",
            operation,
            response.status_code,
            error_code,
            error_message,
        )
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type"),
        )

    try:
        return schema.model_validate(response.json())
    except ValidationError as exc:
        schema_errors = ",".join(
            f"{'.'.join(str(part) for part in error['loc'])}:{error['type']}"
            for error in exc.errors(include_input=False)
        )
        logger.error(
            "monzo_request_failed operation=%s reason=invalid_response "
            "schema_errors=%s",
            operation,
            schema_errors,
        )
        raise HTTPException(
            status_code=502,
            detail="Monzo returned an invalid response",
        ) from exc
    except ValueError as exc:
        logger.error(
            "monzo_request_failed operation=%s reason=invalid_json "
            "exception_type=%s",
            operation,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Monzo returned an invalid response",
        ) from exc


def _raise_unauthorized(detail: str) -> Never:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
