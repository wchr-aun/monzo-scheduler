from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from app.routers.resources import MonzoSession, monzo_session
from app.schemas.tasks import (
    UK_TIMEZONE,
    CancelTransferResponse,
    ScheduleTransferRequest,
    ScheduleTransferResponse,
    ScheduledTransferResponse,
    ScheduledTransfersPageResponse,
    TransferStatus,
)
from app.services.scheduler import (
    InvalidScheduleError,
    ScheduleNotFoundError,
    cancel_scheduled_transfer,
    list_scheduled_transfers,
    schedule_transfer,
)

router = APIRouter(tags=["tasks"])

DEFAULT_TRANSFER_STATUSES = (
    TransferStatus.PENDING,
    TransferStatus.COMPLETED,
    TransferStatus.FAILED,
)


def _parse_transfer_statuses(value: str | None) -> tuple[TransferStatus, ...]:
    if value is None:
        return DEFAULT_TRANSFER_STATUSES

    try:
        statuses = tuple(
            TransferStatus(status.strip()) for status in value.split(",")
        )
    except ValueError as exc:
        allowed = ", ".join(status.value for status in TransferStatus)
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transfer status. Allowed values: {allowed}",
        ) from exc

    if not statuses:
        raise HTTPException(status_code=422, detail="At least one status is required")
    return tuple(dict.fromkeys(statuses))


@router.get(
    "/scheduled-transfers",
    response_model=ScheduledTransfersPageResponse,
)
def get_scheduled_transfers(
        request: Request,
        status: Annotated[
            str | None,
            Query(description="Comma-separated transfer statuses"),
        ] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        authentication: MonzoSession = Depends(monzo_session),
) -> ScheduledTransfersPageResponse:
    statuses = _parse_transfer_statuses(status)
    try:
        page = list_scheduled_transfers(
            request.app.state.session_factory,
            authentication.user_id,
            statuses=statuses,
            limit=limit,
            offset=offset,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Scheduled transfer storage is unavailable",
        ) from exc

    return ScheduledTransfersPageResponse(
        items=[
            ScheduledTransferResponse(
                setup_id=transfer.setup_id,
                transfer_id=transfer.transfer_id,
                scheduled_for=transfer.scheduled_for,
                created_at=transfer.created_at,
                interval=transfer.interval,
                type=transfer.transfer_type,
                amount=transfer.amount,
                pot_id=transfer.pot_id,
                account_id=transfer.account_id,
                setup_status=transfer.setup_status,
                status=transfer.status,
                executed_at=transfer.executed_at,
            )
            for transfer in page.items
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("/schedule-transfer", response_model=ScheduleTransferResponse)
def create_scheduled_transfer(
        transfer_request: ScheduleTransferRequest,
        request: Request,
        authentication: MonzoSession = Depends(monzo_session),
) -> ScheduleTransferResponse:
    try:
        setup, transfer, job = schedule_transfer(
            request.app.state.scheduler,
            request.app.state.session_factory,
            request.app.state.settings,
            authentication.user_id,
            transfer_request,
        )
    except InvalidScheduleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Scheduled transfer storage is unavailable",
        ) from exc

    return ScheduleTransferResponse(
        setup_id=setup.setup_id,
        transfer_id=transfer.transfer_id,
        next_run_at=job.next_run_time.astimezone(UK_TIMEZONE),
    )


@router.delete(
    "/schedule-transfer/{setup_id}",
    response_model=CancelTransferResponse,
)
def cancel_transfer_schedule(
        setup_id: str,
        request: Request,
        authentication: MonzoSession = Depends(monzo_session),
) -> CancelTransferResponse:
    try:
        setup = cancel_scheduled_transfer(
            request.app.state.scheduler,
            request.app.state.session_factory,
            authentication.user_id,
            setup_id,
        )
    except ScheduleNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Scheduled transfer not found"
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Scheduled transfer storage is unavailable",
        ) from exc

    return CancelTransferResponse(setup_id=setup.setup_id)
