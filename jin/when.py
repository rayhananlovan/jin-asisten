from __future__ import annotations

import re
from datetime import datetime, timedelta

_TIME_RE = re.compile(
    r"(?:dalam\s+)?(\d+)\s*(detik|menit|jam|hari)|"
    r"(besok)?\s*(?:jam|pukul)\s*(\d{1,2})(?:[:.](\d{2}))?",
    re.IGNORECASE,
)


def parse_when(text: str, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now()
    blob = text.lower().strip()
    match = _TIME_RE.search(blob)
    if not match:
        return None

    if match.group(1) and match.group(2):
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {
            "detik": timedelta(seconds=amount),
            "menit": timedelta(minutes=amount),
            "jam": timedelta(hours=amount),
            "hari": timedelta(days=amount),
        }[unit]
        return now + delta

    tomorrow = bool(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5) or 0)
    if hour > 23 or minute > 59:
        return None
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if tomorrow or target <= now:
        target += timedelta(days=1)
    return target


def extract_reminder(text: str) -> tuple[str, datetime] | None:
    when = parse_when(text)
    if when is None:
        return None
    task = _TIME_RE.sub(" ", text)
    task = re.sub(r"ingatkan(?:\s+saya)?(?:\s+untuk)?", " ", task, flags=re.IGNORECASE)
    task = re.sub(r"\s+", " ", task).strip(" .,:-")
    return (task or "pengingat"), when
