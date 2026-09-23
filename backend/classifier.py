import os
import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# 1. Guarantee .env loading from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an intelligent email classifier for a university student.
Analyze the email content and extract structured details strictly in JSON format.

Criteria:
- is_important: TRUE for placement, internship, exams, fee deadlines, official notices, assignments, and grade updates. FALSE for clubs, fests, hackathons, sports, marketing, and spam.
- category: One of ["Placement", "Exam", "Academic", "Fee", "General"]
- summary: Crisp 1-2 sentence summary of what happened.
- deadline: Exact deadline date/time mentioned, or null.
- action_required: Immediate direct action required by the student, or null.

Return ONLY a JSON object. No markdown code blocks, no explanation."""


def _clean_json_markdown(raw_text: str) -> str:
    """Safely extracts JSON even if the model outputs markdown code blocks."""
    cleaned = raw_text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned)
    if match:
        return match.group(1).strip()
    return cleaned


def _call_gemini(subject: str, sender: str, body: str) -> Dict[str, Any]:
    from google import genai
    from google.genai import types
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in environment.")
        
    client = genai.Client(api_key=api_key)
    prompt = f"Subject: {subject}\nSender: {sender}\nBody:\n{body[:1500]}"
    
    # 15-second timeout via Client/Model request config
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.1
        )
    )
    
    parsed = json.loads(_clean_json_markdown(response.text))
    return parsed


def _call_groq(subject: str, sender: str, body: str) -> Dict[str, Any]:
    from groq import Groq
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in environment.")
        
    # Set explicit client timeout
    client = Groq(api_key=api_key, timeout=12.0)
    prompt = f"Subject: {subject}\nSender: {sender}\nBody:\n{body[:1500]}"
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )
    
    content = response.choices[0].message.content
    parsed = json.loads(_clean_json_markdown(content))
    return parsed


def _keyword_fallback(subject: str, sender: str, body: str) -> Dict[str, Any]:
    text_to_search = f"{subject} {body}".lower()
    
    # 1. is_important check
    keywords = ["placement", "drive", "exam", "fee", "admit card", "deadline", "hall ticket", "shortlist"]
    is_important = any(kw in text_to_search for kw in keywords)
    
    # 2. category determination
    if "placement" in text_to_search or "internship" in text_to_search:
        category = "Placement"
    elif "exam" in text_to_search or "admit card" in text_to_search or "hall ticket" in text_to_search:
        category = "Exam"
    elif "fee" in text_to_search:
        category = "Fee"
    else:
        category = "Academic" if is_important else "General"
        
    # 3. deadline regex extraction
    deadline = None
    pattern_date = r'(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{0,4})'
    pattern_num = r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
    
    match_date = re.search(pattern_date, text_to_search, re.IGNORECASE)
    match_num = re.search(pattern_num, text_to_search)
    
    if match_date:
        deadline = match_date.group(1).title()
    elif match_num:
        deadline = match_num.group(1)
        
    # 4. action_required
    action_required = "Review email details and take necessary action." if is_important else None
    
    # 5. summary extraction
    lines = [line.strip() for line in body.split('\n') if line.strip()]
    if len(lines) >= 2:
        summary = f"{lines[0]} {lines[1]}"
    elif len(lines) == 1:
        summary = lines[0]
    else:
        summary = subject
        
    return {
        "is_important": is_important,
        "category": category,
        "summary": summary[:250],
        "deadline": deadline,
        "action_required": action_required,
        "execution_tier": "KEYWORD_FALLBACK"
    }


def classify_email(subject: str, sender: str, body: str) -> Dict[str, Any]:
    """
    Cascading Classifier:
    Tier 1 (Gemini) -> Tier 2 (Groq) -> Tier 3 (Keyword Fallback)
    """
    # Tier 1: Gemini
    try:
        result = _call_gemini(subject, sender, body)
        result["execution_tier"] = "GEMINI"
        return result
    except Exception as e:
        logger.warning(f"[Tier 1: Gemini Failed] -> Falling back to Groq. Cause: {e}")
        
    # Tier 2: Groq
    try:
        result = _call_groq(subject, sender, body)
        result["execution_tier"] = "GROQ"
        return result
    except Exception as e:
        logger.warning(f"[Tier 2: Groq Failed] -> Falling back to Keyword Extractor. Cause: {e}")
        
    # Tier 3: Zero-AI Deterministic Net
    return _keyword_fallback(subject, sender, body)



if __name__ == "__main__":
    print("Testing Multi-Tier Classifier Pipeline...\n")
    sample_sub = "Urgent: Amazon Off-Campus Drive 2026 Registration Link"
    sample_sender = "Placement Cell <placements@vitbhopal.ac.in>"
    sample_body = "Dear Students, Amazon has opened registrations for SDE-1 roles. Complete the registration form before 10th September 2026, 11:59 PM."

    result = classify_email(sample_sub, sample_sender, sample_body)
    print("Execution Result:")
    print(json.dumps(result, indent=2))