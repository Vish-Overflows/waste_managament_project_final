import os
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


CAMPUS_TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata"))


def campus_now() -> datetime:
    return datetime.now(CAMPUS_TIMEZONE)


def campus_today() -> date:
    return campus_now().date()


def local_day_start_utc(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=CAMPUS_TIMEZONE).astimezone(UTC)


def local_next_day_start_utc(value: date) -> datetime:
    return local_day_start_utc(value) + timedelta(days=1)


def campus_date(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(CAMPUS_TIMEZONE).date()
