from __future__ import annotations
import re
from datetime import datetime
import dateparser

def parse_quick_add(text: str, *, now: datetime, timezone: str) -> dict:
    match = re.search(r"\s+(?:by|on|at)\s+(.+)$", text, re.IGNORECASE)
    if not match:
        return {"title": text.strip(), "deadline_at": None, "category": "other"}
    title = text[:match.start()].strip(" .") or text.strip()
    phrase = match.group(1).strip(" .")
    parsed = dateparser.parse(phrase, settings={"RELATIVE_BASE": now, "TIMEZONE": timezone, "RETURN_AS_TIMEZONE_AWARE": True})
    return {"title": title[:120] if parsed else text.strip()[:120], "deadline_at": parsed,
            "deadline_phrase": phrase, "category": "other"}

