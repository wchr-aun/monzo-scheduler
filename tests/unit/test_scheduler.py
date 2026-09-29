from datetime import date, datetime, timezone
from unittest.mock import Mock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db.models import Base, ScheduledTransfer, ScheduledTransferSetup
from app.schemas.tasks import ScheduleTransferRequest
from app.services.scheduler import (
    _next_occurrence,
    execute_scheduled_transfer,
    restore_scheduled_transfers,
    schedule_transfer,
)

UK_TIMEZONE = ZoneInfo("Europe/London")


def _monthly_setup(day: int) -> ScheduledTransferSetup:
    return ScheduledTransferSetup(
        setup_id="setup",
        user_id="user",
        scheduled_date=date(2030, 1, day),
        hour=9,
        minute=15,
        interval="monthly",
        transfer_type="deposit",
        amount=100,
        pot_id="pot",
        account_id="account",
        status="active",
    )


@pytest.mark.parametrize(
    ("day", "year", "expected_february_day"),
    [
        (29, 2030, 28),
        (30, 2030, 28),
        (31, 2030, 28),
        (29, 2032, 29),
        (30, 2032, 29),
        (31, 2032, 29),
    ],
)
def test_monthly_occurrence_clamps_then_restores_requested_day(
    day, year, expected_february_day
):
    setup = _monthly_setup(day)
    setup.scheduled_date = date(year, 1, day)
    january = datetime(year, 1, day, 9, 15, tzinfo=UK_TIMEZONE)

    february = _next_occurrence(setup, january)
    march = _next_occurrence(setup, february)

    assert february.astimezone(UK_TIMEZONE) == datetime(
        year, 2, expected_february_day, 9, 15, tzinfo=UK_TIMEZONE
    )
    assert march.astimezone(UK_TIMEZONE) == datetime(
        year, 3, day, 9, 15, tzinfo=UK_TIMEZONE
    )


def test_monthly_occurrence_handles_other_short_months_and_year_boundaries():
    setup = _monthly_setup(31)
    may = datetime(2030, 5, 31, 9, 15, tzinfo=UK_TIMEZONE)
    june = _next_occurrence(setup, may)
    july = _next_occurrence(setup, june)

    assert june.astimezone(UK_TIMEZONE) == datetime(
        2030, 6, 30, 9, 15, tzinfo=UK_TIMEZONE
    )
    assert july.astimezone(UK_TIMEZONE) == datetime(
        2030, 7, 31, 9, 15, tzinfo=UK_TIMEZONE
    )

    december = datetime(2030, 12, 31, 9, 15, tzinfo=UK_TIMEZONE)
    january = _next_occurrence(setup, december)
    assert january.astimezone(UK_TIMEZONE) == datetime(
        2031, 1, 31, 9, 15, tzinfo=UK_TIMEZONE
    )


def test_schedule_transfer_persists_setup_and_pending_occurrence(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    scheduler = Mock()
    job = Mock()
    job.next_run_time = datetime(2030, 1, 31, 9, 15, tzinfo=timezone.utc)
    scheduler.add_job.return_value = job
    settings = Settings("client", "secret", "http://localhost/callback")
    request = ScheduleTransferRequest.model_validate(
        {
            "datetime": "2030-01-31T09:15:00Z",
            "interval": "monthly",
            "type": "deposit",
            "amount": 1250,
            "pot_id": "pot_123",
            "account_id": "acc_123",
        }
    )

    setup, transfer, returned_job = schedule_transfer(
        scheduler,
        factory,
        settings,
        "user_123",
        request,
        now=datetime(2029, 1, 1, tzinfo=UK_TIMEZONE),
    )

    assert UUID(setup.setup_id).version == 6
    assert UUID(transfer.transfer_id).version == 6
    assert returned_job is job
    scheduler.add_job.assert_called_once()
    args, kwargs = scheduler.add_job.call_args
    assert args[:2] == (execute_scheduled_transfer, "date")
    assert kwargs["id"] == transfer.transfer_id
    assert kwargs["args"] == [transfer.transfer_id, scheduler, factory, settings]

    with factory() as session:
        stored_setup = session.get(ScheduledTransferSetup, setup.setup_id)
        stored_transfer = session.get(ScheduledTransfer, transfer.transfer_id)
        assert stored_setup is not None
        assert stored_setup.user_id == "user_123"
        assert stored_setup.status == "active"
        assert stored_setup.scheduled_date.isoformat() == "2030-01-31"
        assert stored_setup.interval == "monthly"
        assert stored_transfer is not None
        assert stored_transfer.setup_id == setup.setup_id
        assert stored_transfer.status == "pending"
        assert stored_transfer.executed_at is None

    restarted_scheduler = Mock()
    restored = restore_scheduled_transfers(
        restarted_scheduler,
        factory,
        settings,
    )
    assert restored == 1
    assert restarted_scheduler.add_job.call_args.kwargs["id"] == (
        transfer.transfer_id
    )
    assert restarted_scheduler.add_job.call_args.kwargs["replace_existing"] is True

    with factory() as session:
        stored_setup = session.get(ScheduledTransferSetup, setup.setup_id)
        assert stored_setup is not None
        stored_setup.status = "deactivated"
        session.commit()

    inactive_scheduler = Mock()
    assert restore_scheduled_transfers(inactive_scheduler, factory, settings) == 0
    inactive_scheduler.add_job.assert_not_called()
    with factory() as session:
        stored_transfer = session.get(ScheduledTransfer, transfer.transfer_id)
        assert stored_transfer is not None
        assert stored_transfer.status == "cancelled"

    engine.dispose()
