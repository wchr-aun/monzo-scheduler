"""Scheduled job operations."""

from datetime import datetime, timedelta, timezone


def log_task(message: str) -> None:
    """Placeholder job function; replace with a pot transfer operation."""
    print(f"Task executed! Message: {message}, Time: {datetime.now(timezone.utc).isoformat()}")


def schedule_message(scheduler, message: str):
    run_at = datetime.now(timezone.utc) + timedelta(seconds=10)
    job = scheduler.add_job(log_task, "date", run_date=run_at, args=[message])
    return job, run_at
