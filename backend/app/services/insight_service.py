from __future__ import annotations

import re
from dataclasses import dataclass


ALLOWED_SUGGESTION_TYPES = {"pad_estimates", "move_focus_window", "adjust_reminder_lead", "protect_routine"}


@dataclass(frozen=True)
class Suggestion:
    type: str
    text: str
    cited_values: list[str]


def validate_suggestions(raw: list[dict], stats: dict) -> list[Suggestion]:
    allowed_numbers = {str(value) for value in stats.values() if isinstance(value, (int, float))}
    valid: list[Suggestion] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get('text'), str):
            continue
        kind, text = item.get("type"), item['text'].strip()
        if kind not in ALLOWED_SUGGESTION_TYPES or not text:
            continue
        numbers = re.findall(r"\d+(?:\.\d+)?", text)
        if any(number not in allowed_numbers for number in numbers):
            continue
        valid.append(Suggestion(kind, text, numbers))
        if len(valid) == 3:
            break
    return valid

