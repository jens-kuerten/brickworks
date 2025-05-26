from datetime import UTC, datetime


def now_utc() -> datetime:
    return datetime.now(UTC)


def convert_datetime_to_iso_8601_with_z_suffix(dt: datetime) -> str:
    # convert dt to utc if it is timezone aware
    if dt.tzinfo is not None:
        dt = dt.astimezone(tz=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
