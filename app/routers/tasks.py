from fastapi import APIRouter, Request

from app.services.scheduler import schedule_message

router = APIRouter(tags=["tasks"])


@router.post("/create-task")
def create_task(request: Request, msg: str = "Hello from endpoint"):
    job, run_at = schedule_message(request.app.state.scheduler, msg)
    return {"status": "success", "job_id": job.id, "scheduled_for": run_at.isoformat()}
