from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from app.services.scheduler import log_task, schedule_message


def test_schedule_message_registers_one_shot_job():
    scheduler = Mock()
    job = object()
    scheduler.add_job.return_value = job
    before = datetime.now(timezone.utc)

    returned_job, run_at = schedule_message(scheduler, "save")

    after = datetime.now(timezone.utc)
    scheduler.add_job.assert_called_once()
    args, kwargs = scheduler.add_job.call_args
    assert args[0] is log_task
    assert args[1] == "date"
    assert kwargs["args"] == ["save"]
    assert before + timedelta(seconds=10) <= run_at <= after + timedelta(seconds=10)
    assert run_at.tzinfo is timezone.utc
    assert returned_job is job


def test_log_task_prints_message_and_utc_time(capsys):
    log_task("scheduled")

    output = capsys.readouterr().out
    assert "Task executed! Message: scheduled, Time:" in output
    assert "+00:00" in output
