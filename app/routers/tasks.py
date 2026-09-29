from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from app.routers.resources import MonzoSession, monzo_session
from app.schemas.tasks import (
    UK_TIMEZONE,
    CancelTransferResponse,
    ScheduleTransferRequest,
    ScheduleTransferResponse,
    ScheduledTransferResponse,
)
from app.services.scheduler import (
    InvalidScheduleError,
    ScheduleNotFoundError,
    cancel_scheduled_transfer,
    list_scheduled_transfers,
    schedule_transfer,
)

router = APIRouter(tags=["tasks"])


@router.get(
    "/scheduled-transfers",
    response_model=list[ScheduledTransferResponse],
)
def get_scheduled_transfers(
    request: Request,
    authentication: MonzoSession = Depends(monzo_session),
) -> list[ScheduledTransferResponse]:
    try:
        transfers = list_scheduled_transfers(
            request.app.state.session_factory,
            authentication.user_id,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Scheduled transfer storage is unavailable",
        ) from exc

    return [
        ScheduledTransferResponse(
            setup_id=transfer.setup_id,
            transfer_id=transfer.transfer_id,
            scheduled_for=transfer.scheduled_for,
            interval=transfer.interval,
            type=transfer.transfer_type,
            amount=transfer.amount,
            pot_id=transfer.pot_id,
            account_id=transfer.account_id,
        )
        for transfer in transfers
    ]


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
