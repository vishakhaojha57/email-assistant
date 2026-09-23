"""
Automated deadline follow-up reminder service.

Periodically inspects `email_analysis` records and dispatches a WhatsApp
reminder for any deadline due within the next 24 hours that hasn't
already been reminded.
"""

import logging
from backend.database import SessionLocal
from backend.crud import get_pending_reminders, mark_reminder_sent
from backend.whatsapp import send_whatsapp_message

logger = logging.getLogger(__name__)


def _format_reminder(record) -> str:
    """
    Build a crisp WhatsApp reminder payload from an EmailAnalysis record.
    """
    subject = record.email.subject if record.email else "N/A"
    category = (record.category or "General").upper()
    deadline = record.deadline or (record.deadline_iso.strftime("%Y-%m-%d %H:%M UTC") if record.deadline_iso else "N/A")
    action = record.action_required or "Review the original email for details."

    return (
        "\u23f0 *DEADLINE REMINDER: 24 HOURS LEFT*\n\n"
        f"\ud83d\udccc *Subject:* {subject}\n"
        f"\ud83d\udcc1 *Category:* {category}\n"
        f"\ud83d\udcc5 *Deadline:* {deadline}\n"
        f"\u2705 *Action:* {action}"
    )


def check_and_send_deadline_reminders():
    """
    Main entry-point called by the scheduler.

    1. Queries for EmailAnalysis records with a deadline in the next 24 h.
    2. Sends a WhatsApp reminder for each.
    3. Marks reminders as sent to avoid duplicates.
    """
    logger.info("\u23f0 Running deadline reminder check...")
    db = SessionLocal()
    try:
        pending = get_pending_reminders(db, window_hours=24)

        if not pending:
            logger.info("No pending deadline reminders.")
            return

        logger.info(f"Found {len(pending)} deadline(s) due within 24 hours.")

        for record in pending:
            message = _format_reminder(record)
            success = send_whatsapp_message(message)

            if success:
                mark_reminder_sent(db, record.id)
                logger.info(f"\u2705 Reminder sent & flagged for analysis ID {record.id}.")
            else:
                logger.warning(f"\u26a0\ufe0f Failed to send reminder for analysis ID {record.id}. Will retry next cycle.")
    except Exception:
        logger.exception("Error during deadline reminder check.")
    finally:
        db.close()
