"""Scheduled job operations."""

from datetime import datetime, timedelta, timezone

from app.observability import get_logger

logger = get_logger(__name__)


def log_task(message: str) -> None:
    """Placeholder job function; replace with a pot transfer operation."""
    logger.info("scheduled_task_executed task_type=message message=%r", message)


def schedule_message(scheduler, message: str):
    run_at = datetime.now(timezone.utc) + timedelta(seconds=10)
    job = scheduler.add_job(log_task, "date", run_date=run_at, args=[message])
    return job, run_at
