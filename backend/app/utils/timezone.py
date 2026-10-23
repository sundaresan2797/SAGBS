from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.config import settings


def get_org_timezone() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_in_org_tz() -> datetime:
    return datetime.now(get_org_timezone())


def today_in_org_tz() -> date:
    return now_in_org_tz().date()
