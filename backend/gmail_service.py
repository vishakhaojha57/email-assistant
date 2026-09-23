import os
import re
import base64
import logging
from typing import List, Dict, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Paths configuration (Root directory se read karega)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials.json')
TOKEN_FILE = os.path.join(BASE_DIR, 'token.json')


def get_gmail_service():
    """Handles OAuth 2.0 authentication with auto-refresh and token recovery."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            logging.warning(f"Corrupted token.json detected: {e}. Re-authenticating...")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logging.info("Gmail OAuth access token successfully refreshed.")
            except Exception as e:
                logging.warning(f"Token refresh failed: {e}. Starting fresh authentication flow...")
                creds = None

        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"Missing {CREDENTIALS_FILE}! Ensure credentials.json is in project root.")
            
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Token save karein
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def clean_html(raw_html: str) -> str:
    """Strips HTML tags, CSS styling, and extra whitespaces to save AI tokens."""
    cleanr = re.compile(r'<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});')
    cleantext = re.sub(cleanr, ' ', raw_html)
    cleantext = re.sub(r'\s+', ' ', cleantext)
    return cleantext.strip()


def extract_body(payload: dict) -> str:
    """Recursively traverses payload parts to extract and decode plain text or HTML."""
    body_text = ""
    
    try:
        # Case 1: Multipart payload
        if 'parts' in payload:
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')
                data = part.get('body', {}).get('data')

                if mime_type == 'text/plain' and data:
                    body_text += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                elif mime_type == 'text/html' and not body_text and data:
                    raw_html = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    body_text += clean_html(raw_html)
                elif 'parts' in part:
                    body_text += extract_body(part)

        # Case 2: Single-part payload
        else:
            data = payload.get('body', {}).get('data')
            if data:
                decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                if payload.get('mimeType') == 'text/html':
                    body_text = clean_html(decoded)
                else:
                    body_text = decoded

    except Exception as e:
        logging.error(f"Error decoding email body: {e}")
        return ""

    return clean_html(body_text)


def fetch_unread_emails(max_results: int = 5) -> List[Dict[str, str]]:
    """
    Fetches unread emails with full exception handling.
    Returns: List of dicts containing id, sender, subject, date, and cleaned body.
    """
    emails_data = []

    try:
        service = get_gmail_service()
        results = service.users().messages().list(
            userId='me',
            q='is:unread',
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])
        if not messages:
            logging.info("Inbox clean: No unread emails found.")
            return []

        logging.info(f"Found {len(messages)} unread email(s). Extracting data...")

        for msg in messages:
            try:
                message = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='full'
                ).execute()

                payload = message.get('payload', {})
                headers = payload.get('headers', [])

                subject = "No Subject"
                sender = "Unknown Sender"
                date = "Unknown Date"

                for header in headers:
                    name = header.get('name', '').lower()
                    if name == 'subject':
                        subject = header.get('value', '')
                    elif name == 'from':
                        sender = header.get('value', '')
                    elif name == 'date':
                        date = header.get('value', '')

                body = extract_body(payload)

                emails_data.append({
                    "id": msg['id'],
                    "sender": sender,
                    "subject": subject,
                    "date": date,
                    "body": body[:1200]  # First 1200 chars - optimal for AI summary
                })

            except HttpError as http_err:
                logging.error(f"Failed fetching message ID {msg['id']}: {http_err}")
                continue
            except Exception as e:
                logging.error(f"Unexpected error processing email ID {msg['id']}: {e}")
                continue

    except HttpError as http_err:
        logging.error(f"Gmail API service call failed: {http_err}")
    except Exception as e:
        logging.error(f"Fatal error during email ingestion: {e}")

    return emails_data


if __name__ == '__main__':
    logging.info("Testing robust Gmail Ingestion...")
    unread_emails = fetch_unread_emails(max_results=3)
    for idx, mail in enumerate(unread_emails, 1):
        print(f"\n--- Email {idx} ---")
        print(f"ID: {mail['id']}")
        print(f"Sender: {mail['sender']}")
        print(f"Subject: {mail['subject']}")
        print(f"Clean Body Sample: {mail['body'][:200]}...")