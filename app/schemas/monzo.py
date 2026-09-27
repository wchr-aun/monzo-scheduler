from pydantic import BaseModel, ConfigDict, Field


class MonzoTokenResponse(BaseModel):
    """Token payload returned by Monzo's OAuth authorization-code exchange."""

    model_config = ConfigDict(extra="ignore")

    access_token: str = Field(min_length=1)
    client_id: str | None = None
    expires_in: int = Field(strict=True, gt=0)
    refresh_token: str | None = None
    token_type: str = Field(default="Bearer", min_length=1)
    user_id: str = Field(min_length=1)
