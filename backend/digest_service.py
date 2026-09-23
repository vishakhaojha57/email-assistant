"""
Daily consolidated email digest service.

Aggregates all processed emails from the past 24 hours into a single
concise WhatsApp message for a quick end-of-day overview.
"""

import logging
from backend.database import SessionLocal
from backend.crud import get_daily_digest_records
from backend.whatsapp import send_whatsapp_message

logger = logging.getLogger(__name__)


def _format_digest(records) -> str:
    """
    Build a consolidated WhatsApp digest from a list of
    (ProcessedEmail, EmailAnalysis) tuples.
    """
    lines = [
        "\ud83d\udccb *DAILY EMAIL DIGEST* \ud83d\udccb",
        "Here is a summary of your inbox updates today:\n",
    ]

    for idx, (email, analysis) in enumerate(records, start=1):
        subject = email.subject or "No Subject"
        category = (analysis.category or "General").upper()
        deadline = analysis.deadline or "None"
        summary = analysis.summary or "No summary available."

        lines.append(
            f"{idx}. *{subject}*\n"
            f"   \ud83c\udff7\ufe0f Category: {category} | \ud83d\udcc5 Deadline: {deadline}\n"
            f"   \ud83d\udcdd {summary}\n"
        )

    lines.append(f"\n\ud83d\udce8 Total emails processed: {len(records)}")
    return "\n".join(lines)


def send_daily_digest():
    """
    Main entry-point called by the scheduler or the /trigger/digest API.

    1. Queries for all processed emails in the last 24 hours.
    2. Formats them into a consolidated digest.
    3. Sends via WhatsApp.
    """
    logger.info("\ud83d\udccb Running daily digest generation...")
    db = SessionLocal()
    try:
        records = get_daily_digest_records(db, hours=24)

        if not records:
            logger.info("\u2139\ufe0f No processed records found for today's digest.")
            return

        logger.info(f"Compiling digest for {len(records)} email(s).")
        message = _format_digest(records)
        success = send_whatsapp_message(message)

        if success:
            logger.info("\u2705 Daily digest sent successfully!")
        else:
            logger.warning("\u26a0\ufe0f Failed to send daily digest via WhatsApp.")
    except Exception:
        logger.exception("Error during daily digest generation.")
    finally:
        db.close()
