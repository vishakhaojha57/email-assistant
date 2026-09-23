import os
import logging
import requests
from typing import Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# Root .env ensure karein
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

WHATSAPP_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
RECIPIENT_NUMBER = os.getenv("RECIPIENT_PHONE_NUMBER")


def format_whatsapp_message(ai_result: Dict[str, Any], subject: str = "") -> str:
    """
    Transforms structured AI output into an actionable, crisp WhatsApp alert.
    """
    category = ai_result.get("category", "General Alert").upper()
    summary = ai_result.get("summary", "No summary available.")
    deadline = ai_result.get("deadline") or "Not Specified / No Deadline"
    action = ai_result.get("action_required") or "Read the full email for instructions."
    tier = ai_result.get("execution_tier", "AI")

    # Clean formatting with emojis
    message = (
        f"🔴 *IMPORTANT UPDATE: {category}*\n\n"
        f"📌 *Summary:* {summary}\n"
        f"📅 *Deadline:* {deadline}\n"
        f"✅ *Action Required:* {action}\n\n"
        f"⚡ _Processed via {tier} Engine_"
    )
    return message


def send_whatsapp_message(body_text: str) -> bool:
    """
    Low-level helper that sends a plain-text WhatsApp message via Meta Cloud API.
    Returns True on success, False otherwise.
    """
    if not all([WHATSAPP_TOKEN, PHONE_NUMBER_ID, RECIPIENT_NUMBER]):
        logger.error("Missing WhatsApp credentials in .env file! Check tokens.")
        return False

    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": RECIPIENT_NUMBER,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": body_text
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()

        if response.status_code == 200:
            msg_id = data.get("messages", [{}])[0].get("id")
            logger.info(f"✅ WhatsApp Message Delivered Successfully! (ID: {msg_id})")
            return True
        else:
            logger.error(f"❌ WhatsApp API Failed: Status {response.status_code} - {data}")
            return False

    except requests.exceptions.RequestException as req_err:
        logger.error(f"Network error while sending WhatsApp message: {req_err}")
        return False


def send_whatsapp_alert(ai_result: Dict[str, Any], subject: str = "") -> bool:
    """
    Sends structured alert via Meta WhatsApp Cloud API.
    Returns True if sent, False if dropped or failed.
    """
    # 1. Unimportant emails ko drop karo (WhatsApp spam na ho)
    if not ai_result.get("is_important", False):
        logger.info("Email classified as NOT IMPORTANT. Skipping WhatsApp dispatch.")
        return False

    body_text = format_whatsapp_message(ai_result, subject)
    return send_whatsapp_message(body_text)


if __name__ == "__main__":
    print("Testing WhatsApp Service with Mock AI Output...\n")
    mock_ai_output = {
        "is_important": True,
        "category": "Placement",
        "summary": "Amazon off-campus registration link is live for 2026 batch.",
        "deadline": "10th September 2026, 11:59 PM",
        "action_required": "Submit registration form before portal closes.",
        "execution_tier": "GEMINI"
    }

    success = send_whatsapp_alert(mock_ai_output, subject="Amazon Placement Drive")
    if success:
        print("\n🚀 Check your WhatsApp! Message should be received.")