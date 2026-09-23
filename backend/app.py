import sys
from pathlib import Path

# Ensure project root is added to sys.path at the very top
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from backend.database import SessionLocal
from backend.models import ProcessedEmail, EmailAnalysis
from backend.main import process_inbox_pipeline
from backend.reminder_service import check_and_send_deadline_reminders
from backend.digest_service import send_daily_digest

from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pydantic import BaseModel

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Trigger email ingestion every 15 minutes
    scheduler.add_job(process_inbox_pipeline, 'interval', minutes=15, id='inbox_poll_job', replace_existing=True)
    # Trigger deadline reminder checks every 30 minutes
    scheduler.add_job(check_and_send_deadline_reminders, 'interval', minutes=30, id='deadline_reminder_job', replace_existing=True)
    # Daily digest at 20:00 UTC (01:30 AM IST next day)
    scheduler.add_job(send_daily_digest, 'cron', hour=20, minute=0, id='daily_digest_job', replace_existing=True)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="Email to WhatsApp Assistant API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Trigger Endpoints ───────────────────────────────────────────────

@app.post("/trigger")
def trigger_pipeline(background_tasks: BackgroundTasks):
    """
    Triggers the email ingestion pipeline in the background.
    """
    background_tasks.add_task(process_inbox_pipeline)
    return {"status": "success", "message": "Email ingestion pipeline started in the background."}


@app.post("/trigger/sync")
def trigger_sync(background_tasks: BackgroundTasks):
    """
    Alias for /trigger – used by the dashboard 'Sync Now' button.
    """
    background_tasks.add_task(process_inbox_pipeline)
    return {"status": "success", "message": "Email sync started in the background."}


@app.post("/trigger/digest")
def trigger_digest(background_tasks: BackgroundTasks):
    """
    Triggers the daily digest generation on demand.
    """
    background_tasks.add_task(send_daily_digest)
    return {"status": "success", "message": "Daily digest generation started in the background."}


class SchedulerUpdate(BaseModel):
    interval_minutes: int
    is_paused: bool

@app.get("/settings/scheduler")
def get_scheduler_settings():
    job = scheduler.get_job('inbox_poll_job')
    if not job:
        return {"status": "error", "message": "Job not found"}
    
    interval_minutes = job.trigger.interval.total_seconds() / 60 if hasattr(job.trigger, 'interval') else 15
    is_paused = not job.next_run_time
    
    return {
        "status": "success",
        "data": {
            "interval_minutes": int(interval_minutes),
            "is_paused": is_paused,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None
        }
    }

@app.post("/settings/scheduler")
def update_scheduler_settings(payload: SchedulerUpdate):
    job = scheduler.get_job('inbox_poll_job')
    if not job:
        return {"status": "error", "message": "Job not found"}
        
    if payload.is_paused:
        scheduler.pause_job('inbox_poll_job')
    else:
        scheduler.resume_job('inbox_poll_job')
        
    # Update interval
    scheduler.reschedule_job('inbox_poll_job', trigger='interval', minutes=payload.interval_minutes)
    
    # Reschedule can unpause the job, so if it's meant to be paused, we must re-pause it
    if payload.is_paused:
        scheduler.pause_job('inbox_poll_job')
        
    job = scheduler.get_job('inbox_poll_job')
    is_paused = not job.next_run_time
        
    return {
        "status": "success", 
        "message": "Scheduler updated",
        "data": {
            "interval_minutes": payload.interval_minutes,
            "is_paused": is_paused,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None
        }
    }


# ─── Status Endpoint ─────────────────────────────────────────────────

@app.get("/status")
def get_status(db: Session = Depends(get_db)):
    """
    Returns aggregate stats for the dashboard metric cards.
    """
    total_processed = db.query(func.count(ProcessedEmail.id)).filter(
        ProcessedEmail.status == "PROCESSED"
    ).scalar() or 0

    important_count = db.query(func.count(EmailAnalysis.id)).filter(
        EmailAnalysis.category.in_(["Placement", "Exam", "Scholarship", "Fee", "Internship"])
    ).scalar() or 0

    now = datetime.now(timezone.utc)
    upcoming_deadlines = db.query(func.count(EmailAnalysis.id)).filter(
        EmailAnalysis.deadline_iso.isnot(None),
        EmailAnalysis.deadline_iso > now,
    ).scalar() or 0

    return {
        "status": "success",
        "data": {
            "total_processed": total_processed,
            "important_alerts": important_count,
            "upcoming_deadlines": upcoming_deadlines,
        }
    }


# ─── History / Feed Endpoints ────────────────────────────────────────

def _serialize_email(email: ProcessedEmail) -> dict:
    """Shared serializer for email history records."""
    analysis_data = None
    if email.analysis:
        analysis_data = {
            "category": email.analysis.category,
            "summary": email.analysis.summary,
            "deadline": email.analysis.deadline,
            "deadline_iso": email.analysis.deadline_iso.isoformat() if email.analysis.deadline_iso else None,
            "action_required": email.analysis.action_required,
            "execution_tier": email.analysis.execution_tier,
            "is_important": email.analysis.category in (
                "Placement", "Exam", "Scholarship", "Fee", "Internship"
            ) if email.analysis.category else False,
        }

    return {
        "id": email.id,
        "gmail_message_id": email.gmail_message_id,
        "sender": email.sender,
        "subject": email.subject,
        "status": email.status,
        "processed_at": email.processed_at.isoformat() if email.processed_at else None,
        "analysis": analysis_data,
    }


@app.get("/history")
def get_history(limit: int = 50, db: Session = Depends(get_db)):
    """
    Returns the history of processed emails.
    """
    emails = db.query(ProcessedEmail).order_by(desc(ProcessedEmail.processed_at)).limit(limit).all()
    result = [_serialize_email(e) for e in emails]
    return {"status": "success", "count": len(result), "data": result}


@app.get("/emails/history")
def get_emails_history(limit: int = 50, db: Session = Depends(get_db)):
    """
    Alias for /history – used by the dashboard feed component.
    """
    emails = db.query(ProcessedEmail).order_by(desc(ProcessedEmail.processed_at)).limit(limit).all()
    result = [_serialize_email(e) for e in emails]
    return {"status": "success", "count": len(result), "data": result}
