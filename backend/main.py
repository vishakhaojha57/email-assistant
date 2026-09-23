import sys
import os
# Add the project root to sys.path so we can run this script directly (e.g. python backend/main.py)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from backend.gmail_service import fetch_unread_emails
from backend.pre_filter import pre_filter_email
from backend.classifier import classify_email
from backend.whatsapp import send_whatsapp_alert
from backend.database import SessionLocal
from backend.crud import is_email_already_processed, save_processed_email
from backend.date_utils import parse_to_iso_datetime



logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def process_inbox_pipeline():
    logger.info("🔍 Checking for unread university emails...")
    emails = fetch_unread_emails()

    if not emails:
        logger.info("No unread emails found.")
        return

    db = SessionLocal()
    try:
        for email in emails:
            message_id = email.get("id")
            subject = email.get("subject", "")
            sender = email.get("sender", "")
            body = email.get("body", "")
            
            if not message_id:
                logger.warning("Email has no ID, skipping...")
                continue
                
            if is_email_already_processed(db, message_id):
                logger.info(f"⏭️ Skipping already processed email ID: {message_id}")
                continue

            logger.info(f"\n📧 Processing: {subject[:50]}... from {sender}")

            # Stage 1: Deterministic Pre-Filter
            should_proceed, filter_reason = pre_filter_email(subject, sender, body)
            if not should_proceed:
                logger.info(f"⏭️ {filter_reason}")
                save_processed_email(
                    db=db,
                    gmail_message_id=message_id,
                    sender=sender,
                    subject=subject,
                    analysis=None,
                    status="SKIPPED_BY_FILTER"
                )
                continue

            # Stage 2: Cascading Classification & Summary
            logger.info("🤖 Analyzing content through AI/Fallback engine...")
            analysis = classify_email(subject, sender, body)

            # Stage 2b: Deadline Normalization (log only; persistence handled in crud.py)
            deadline_raw = analysis.get("deadline")
            deadline_iso = parse_to_iso_datetime(deadline_raw)
            if deadline_iso:
                logger.info(f"📅 Deadline parsed: '{deadline_raw}' → {deadline_iso.isoformat()}")
            elif deadline_raw:
                logger.info(f"📅 Deadline could not be parsed: '{deadline_raw}'")
            else:
                logger.info("📅 No deadline found in analysis.")

            # Stage 3: WhatsApp Alert
            if analysis.get("is_important", False):
                logger.info("🚀 Important notice detected! Sending WhatsApp alert...")
                send_whatsapp_alert(analysis, subject=subject)
            else:
                logger.info("ℹ️ Email classified as General/Low priority. WhatsApp alert skipped.")
                
            # Stage 4: Database Persistence
            save_processed_email(
                db=db,
                gmail_message_id=message_id,
                sender=sender,
                subject=subject,
                analysis=analysis,
                status="PROCESSED"
            )
            logger.info("✅ Email saved to database.")
    finally:
        db.close()


scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler.add_job(
        process_inbox_pipeline,
        'interval',
        minutes=15,
        id='inbox_poll_job',
        replace_existing=True
    )
    scheduler.start()
    yield
    # Shutdown
    scheduler.shutdown()

app = FastAPI(
    title="Email to WhatsApp Assistant API",
    version="1.0.0",
    lifespan=lifespan
)

if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Starting Email-to-WhatsApp Master Pipeline (Phase 2 with DB Deduplication)...")
    # Using uvicorn to run the FastAPI app so the lifespan context manager triggers
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)