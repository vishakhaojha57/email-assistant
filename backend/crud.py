from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from backend.models import ProcessedEmail, EmailAnalysis
from backend.date_utils import parse_to_iso_datetime

def is_email_already_processed(db: Session, gmail_message_id: str) -> bool:
    """
    Returns True if the gmail_message_id exists in the processed_emails table.
    """
    return db.query(ProcessedEmail).filter(ProcessedEmail.gmail_message_id == gmail_message_id).first() is not None

def save_processed_email(
    db: Session, 
    gmail_message_id: str, 
    sender: str, 
    subject: str, 
    analysis: dict | None = None, 
    status: str = "PROCESSED"
):
    """
    Atomically commits the email record and its associated EmailAnalysis record
    (if analysis dict is provided).
    """
    db_email = ProcessedEmail(
        gmail_message_id=gmail_message_id,
        sender=sender,
        subject=subject,
        status=status
    )
    
    if analysis:
        deadline_raw = analysis.get("deadline")
        deadline_iso = parse_to_iso_datetime(deadline_raw)

        db_analysis = EmailAnalysis(
            category=analysis.get("category"),
            summary=analysis.get("summary"),
            deadline=deadline_raw,
            deadline_iso=deadline_iso,
            action_required=analysis.get("action_required"),
            execution_tier=analysis.get("execution_tier"),
            email=db_email
        )
        db.add(db_analysis)
    else:
        db.add(db_email)
        
    db.commit()
    db.refresh(db_email)
    return db_email


def get_pending_reminders(db: Session, window_hours: int = 24) -> list[EmailAnalysis]:
    """
    Returns EmailAnalysis records whose deadline falls within the next
    `window_hours` and haven't had a reminder sent yet.
    """
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=window_hours)

    return (
        db.query(EmailAnalysis)
        .filter(
            EmailAnalysis.reminder_sent == False,
            EmailAnalysis.deadline_iso.isnot(None),
            EmailAnalysis.deadline_iso > now,
            EmailAnalysis.deadline_iso <= window_end,
        )
        .all()
    )


def mark_reminder_sent(db: Session, analysis_id: int):
    """
    Flags a reminder as sent so it won't be dispatched again.
    """
    record = db.query(EmailAnalysis).filter(EmailAnalysis.id == analysis_id).first()
    if record:
        record.reminder_sent = True
        db.commit()


def get_daily_digest_records(db: Session, hours: int = 24) -> list[tuple[ProcessedEmail, EmailAnalysis]]:
    """
    Returns (ProcessedEmail, EmailAnalysis) pairs for emails processed
    within the last `hours` that have status 'PROCESSED'.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    return (
        db.query(ProcessedEmail, EmailAnalysis)
        .join(EmailAnalysis, ProcessedEmail.id == EmailAnalysis.email_id)
        .filter(
            ProcessedEmail.processed_at >= cutoff,
            ProcessedEmail.status == "PROCESSED",
        )
        .order_by(ProcessedEmail.processed_at.desc())
        .all()
    )

