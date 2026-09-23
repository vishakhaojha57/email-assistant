"""
Deadline parsing & ISO-8601 normalization utilities.

Converts raw relative / natural-language deadline strings produced by the
AI classifier into timezone-aware UTC datetime objects suitable for
database storage and downstream scheduling.
"""

import re
import logging
from datetime import datetime, timedelta, timezone

from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)

# Phrases that mean "no deadline"
_NO_DEADLINE_PHRASES = {
    "not specified",
    "none",
    "no deadline",
    "n/a",
    "na",
    "unspecified",
    "no due date",
    "not applicable",
    "not mentioned",
}

# Words to strip before parsing
_STRIP_PREFIXES = re.compile(
    r"^\s*(by|before|deadline[:\s]*|due[:\s]*|until)\s+",
    re.IGNORECASE,
)

# Relative-time patterns  (e.g. "tomorrow 5 PM", "next friday")
_RELATIVE_PATTERNS: list[tuple[re.Pattern, object]] = [
    (re.compile(r"\btomorrow\b", re.IGNORECASE), timedelta(days=1)),
    (re.compile(r"\btoday\b", re.IGNORECASE), timedelta(days=0)),
    (re.compile(r"\bnext\s+week\b", re.IGNORECASE), timedelta(weeks=1)),
    (re.compile(r"\bin\s+(\d+)\s+days?\b", re.IGNORECASE), None),  # handled specially
    (re.compile(r"\bin\s+(\d+)\s+hours?\b", re.IGNORECASE), None),
]


def _try_relative_parse(text: str, now: datetime) -> datetime | None:
    """Attempt to resolve relative expressions like 'tomorrow 5 PM'."""
    lower = text.lower()

    # --- "tomorrow [time]" / "today [time]" ---
    for pattern, delta in _RELATIVE_PATTERNS[:2]:
        match = pattern.search(lower)
        if match:
            base_date = (now + delta).date()
            # Strip the matched word and try to parse a time from the remainder
            remainder = pattern.sub("", text).strip()
            if remainder:
                try:
                    parsed_time = dateutil_parser.parse(remainder, fuzzy=True).time()
                    return datetime.combine(base_date, parsed_time, tzinfo=timezone.utc)
                except (ValueError, OverflowError):
                    pass
            # No parseable time – default to end-of-day
            return datetime.combine(base_date, datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc)

    # --- "next week" ---
    if _RELATIVE_PATTERNS[2][0].search(lower):
        base_date = (now + timedelta(weeks=1)).date()
        return datetime.combine(base_date, datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc)

    # --- "in N days" ---
    m = _RELATIVE_PATTERNS[3][0].search(lower)
    if m:
        days = int(m.group(1))
        base_date = (now + timedelta(days=days)).date()
        return datetime.combine(base_date, datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc)

    # --- "in N hours" ---
    m = _RELATIVE_PATTERNS[4][0].search(lower)
    if m:
        hours = int(m.group(1))
        return now + timedelta(hours=hours)

    return None


def parse_to_iso_datetime(deadline_raw: str | None) -> datetime | None:
    """
    Convert a raw deadline string into a timezone-aware UTC ``datetime``.

    Parameters
    ----------
    deadline_raw : str | None
        The raw deadline text produced by the AI analysis step.

    Returns
    -------
    datetime | None
        A timezone-aware UTC datetime, or ``None`` if the input is empty,
        indicates "no deadline", or cannot be parsed.
    """
    if not deadline_raw or not isinstance(deadline_raw, str):
        return None

    cleaned = deadline_raw.strip()
    if not cleaned:
        return None

    # Check for "no deadline" sentinel phrases
    if cleaned.lower() in _NO_DEADLINE_PHRASES:
        return None

    # Strip prefix filler words ("by", "before", "deadline:", etc.)
    cleaned = _STRIP_PREFIXES.sub("", cleaned).strip()

    now = datetime.now(timezone.utc)

    # 1. Try relative / natural-language patterns first
    result = _try_relative_parse(cleaned, now)
    if result is not None:
        return result

    # 2. Fall back to dateutil fuzzy parsing
    try:
        parsed = dateutil_parser.parse(cleaned, fuzzy=True)
        # Ensure timezone-awareness (assume UTC if naïve)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, OverflowError) as exc:
        logger.warning(
            "Could not parse deadline string %r – returning None. Error: %s",
            deadline_raw,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Verification harness
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_cases = [
        ("10th October 2026, 11:59 PM", True),
        ("Tomorrow 5 PM", True),
        ("2026-09-30", True),
        ("No deadline", False),
        (None, False),
        ("", False),
        ("Not Specified", False),
        ("by Friday 3 PM", True),
        ("in 3 days", True),
    ]

    print("=" * 60)
    print("Deadline Parser – Verification Harness")
    print("=" * 60)
    for raw, should_parse in test_cases:
        result = parse_to_iso_datetime(raw)
        status = "PASS" if (result is not None) == should_parse else "FAIL"
        iso_str = result.isoformat() if result else "None"
        print(f"  [{status}]  {str(raw):<40s} -> {iso_str}")
    print("=" * 60)
