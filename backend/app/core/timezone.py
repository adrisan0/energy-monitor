from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def utc_now() -> datetime:
    return datetime.now(UTC)


def local_zone() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=local_zone()).astimezone(UTC)
    return value.astimezone(UTC)


def db_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_local(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(local_zone())


def local_date_time(value: datetime) -> tuple[datetime, date, time]:
    local = to_local(value)
    return local, local.date(), local.timetz().replace(tzinfo=None)
