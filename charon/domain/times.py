"""Time helpers shared by feed parsing, cursors and storage."""

from datetime import UTC, datetime


def to_utc(value: datetime) -> datetime:
    """`value` in UTC; a time without a zone is taken as UTC.

    Raises ValueError for times that can't be expressed in UTC, e.g. year 1 at +01:00.
    """
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        return aware.astimezone(UTC)
    except OverflowError as exc:
        raise ValueError(f"{value.isoformat()} is out of range") from exc
