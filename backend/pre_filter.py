import re
from typing import Tuple

# 1. Internal Trusted Domains (Official University)
TRUSTED_INTERNAL_DOMAINS = [
    "vitbhopal.ac.in",
    "ac.in",
    "edu",
    "university.edu"
]

# 2. Whitelisted Genuine External Platforms (Students ke kaam ke portals)
WHITELISTED_EXTERNAL_DOMAINS = [
    "nptel.iitm.ac.in",
    "swayam.gov.in",
    "coursera.org",
    "joinsuperset.com",
    "myamcat.com",
    "hackerearth.com",
    "unstop.com"
]

# 3. High-Priority Signals (Inke milne par email drop NAHI hogi)
CRITICAL_KEYWORDS = [
    r"\bplacement\b", r"\binternship\b", r"\bdrive\b", r"\bexam\b", 
    r"\bfee\b", r"\bhall ticket\b", r"\badmit card\b", r"\bdeadline\b", 
    r"\bshortlist\b", r"\binterview\b", r"\botp\b", r"\bresult\b"
]

# 4. Immediate Noise / Promotional Patterns (Drop candidates)
NOISE_KEYWORDS = [
    r"\bclub\b", r"\bfest\b", r"\bganshutsav\b", r"\bganeshotsav\b", 
    r"\bcelebration\b", r"\bcultural\b", r"\bwebinar\b", r"\bswiggy\b", 
    r"\bzomato\b", r"\bflat\s*\d+%\s*off\b", r"\bcoupon\b", r"\bdiscount\b",
    r"\bnewsletter\b", r"\bpaid\s*course\b"
]


def extract_sender_domain(sender: str) -> str:
    """Sender string se domain extract karta hai (e.g. 'xyz@vitbhopal.ac.in' -> 'vitbhopal.ac.in')."""
    match = re.search(r'@([\w.-]+)', sender)
    return match.group(1).lower() if match else ""


def pre_filter_email(subject: str, sender: str, body: str) -> Tuple[bool, str]:
    """
    Layer 1 Pre-Filter:
    Decides whether an email requires deep LLM processing or can be discarded locally.
    
    Returns:
        (should_proceed: bool, reason: str)
    """
    sender_lower = sender.lower()
    content_sample = f"{subject} {body[:400]}".lower()
    sender_domain = extract_sender_domain(sender)

    # --- Rule 1: High-Priority Safety Net ---
    # Agar critical academic/placement terms hain toh risk nahi lena, AI ko pass karo
    for pattern in CRITICAL_KEYWORDS:
        if re.search(pattern, content_sample):
            return True, f"High-priority keyword detected ('{pattern}'). Routing to AI."

    # --- Rule 2: Noise / Spam Filter ---
    # Fest, club, promotional circulars ko yahin drop karo
    for pattern in NOISE_KEYWORDS:
        if re.search(pattern, content_sample):
            return False, f"Dropped: Noise or promotional pattern ('{pattern}') matched."

    # --- Rule 3: Sender Origin Classification ---
    # 3A: Internal University Domain
    if any(sender_domain.endswith(domain) for domain in TRUSTED_INTERNAL_DOMAINS):
        # Internal email without direct noise keyword -> pass to AI
        return True, "Internal university sender. Passed to AI for deep inspection."

    # 3B: Genuine Whitelisted External Domain (NPTEL, Unstop, etc.)
    if any(sender_domain.endswith(domain) for domain in WHITELISTED_EXTERNAL_DOMAINS):
        return True, f"Verified external academic/career portal ({sender_domain}). Routing to AI."

    # 3C: Unknown External Domain (Gmail, promotional companies, etc.)
    # Agar na critical keyword mila, aur unknown external source hai -> Drop
    return False, f"Dropped: Untrusted external sender ({sender_domain}) without academic relevance."


if __name__ == "__main__":
    test_suite = [
        {
            "desc": "Internal Placement Mail (No External Tag)",
            "sender": "CDC Office <placements@vitbhopal.ac.in>",
            "subject": "Urgent: Amazon Shortlisted Candidates List",
            "body": "Please find the interview schedule attached."
        },
        {
            "desc": "Whitelisted External Portal",
            "sender": "NPTEL Team <onlinecourses@nptel.iitm.ac.in>",
            "subject": "Exam City Allocation Notice",
            "body": "Hall tickets are available on the portal."
        },
        {
            "desc": "Fake External Placement / Promo Mail",
            "sender": "CareerBoost Ads <promotions@learntech24.com>",
            "subject": "Special 50% discount on Placement Prep Webinar",
            "body": "Buy our course now and get flat discount."
        },
        {
            "desc": "Internal Club Event",
            "sender": "Music Society <music.club@vitbhopal.ac.in>",
            "subject": "Cultural Fest 2026 Auditions Open!",
            "body": "Join the club cultural fest celebrations this weekend."
        },
        {
            "desc": "Random External Newsletter",
            "sender": "Updates <newsletter@medium.com>",
            "subject": "Top 10 Tech Stories of the Week",
            "body": "Here is what happened in tech this week."
        }
    ]

    print("Running Layer 1 Pre-Filter Tests...\n")
    for test in test_suite:
        proceed, reason = pre_filter_email(test["subject"], test["sender"], test["body"])
        decision = "✅ PASS TO AI" if proceed else "❌ DROP"
        print(f"Test: {test['desc']}")
        print(f"Subject: {test['subject']}")
        print(f"Sender: {test['sender']}")
        print(f"Decision: {decision} | Reason: {reason}\n" + "-" * 60)