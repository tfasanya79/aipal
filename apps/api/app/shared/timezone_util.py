"""User-local calendar helpers."""

from datetime import date, datetime
from zoneinfo import ZoneInfo


def user_local_today(tz_name: str | None) -> date:
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()
