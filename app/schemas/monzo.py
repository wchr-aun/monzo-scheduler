from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, WithJsonSchema


def _valid_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value


Timestamp = Annotated[
    str,
    AfterValidator(_valid_timestamp),
    WithJsonSchema({"type": "string", "format": "date-time"}),
]


class MonzoTokenResponse(BaseModel):
    """Token payload returned by Monzo's OAuth authorization-code exchange."""

    model_config = ConfigDict(extra="ignore")

    access_token: str = Field(min_length=1)
    client_id: str | None = None
    expires_in: int = Field(strict=True, gt=0)
    refresh_token: str | None = None
    token_type: str = Field(default="Bearer", min_length=1)
    user_id: str = Field(min_length=1)


class Account(BaseModel):
    """Account details exposed by this service."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    description: str
    created: Timestamp


class AccountsResponse(BaseModel):
    """Response returned by the accounts endpoint."""

    model_config = ConfigDict(extra="ignore")

    accounts: list[Account]


class BalanceResponse(BaseModel):
    """Balance details exposed by this service."""

    model_config = ConfigDict(extra="ignore")

    balance: int = Field(strict=True)
    total_balance: int = Field(strict=True)
    currency: str = Field(min_length=3, max_length=3)
    spend_today: int = Field(strict=True)


class Pot(BaseModel):
    """Savings pot details exposed by this service."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    name: str
    style: str
    balance: int = Field(strict=True)
    currency: str = Field(min_length=3, max_length=3)
    created: Timestamp
    updated: Timestamp
    deleted: bool = Field(strict=True)


class PotsResponse(BaseModel):
    """Response returned by the pots endpoint."""

    model_config = ConfigDict(extra="ignore")

    pots: list[Pot]
