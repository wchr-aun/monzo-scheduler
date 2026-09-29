from datetime import datetime as DateTime
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

UK_TIMEZONE = ZoneInfo("Europe/London")


class TransferInterval(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class TransferType(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"


class ScheduleTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datetime: DateTime
    interval: TransferInterval
    type: TransferType
    amount: int = Field(strict=True, gt=0)
    pot_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)

    @field_validator("datetime")
    @classmethod
    def validate_uk_datetime(cls, value: DateTime) -> DateTime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must include the UK UTC offset")

        uk_value = value.astimezone(UK_TIMEZONE)
        if value.replace(tzinfo=None) != uk_value.replace(tzinfo=None):
            raise ValueError("datetime must represent local UK time")
        if value.second != 0 or value.microsecond != 0:
            raise ValueError("datetime must be aligned to a whole minute")
        return uk_value


class ScheduleTransferResponse(BaseModel):
    status: str = "scheduled"
    setup_id: str
    transfer_id: str
    next_run_at: DateTime


class ScheduledTransferResponse(BaseModel):
    setup_id: str
    transfer_id: str
    scheduled_for: DateTime
    interval: TransferInterval
    type: TransferType
    amount: int
    pot_id: str
    account_id: str


class CancelTransferResponse(BaseModel):
    setup_id: str
    status: str = "deactivated"
