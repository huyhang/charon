from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

Clock = Callable[[], datetime]
IdFactory = Callable[[], str]


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_uuid() -> str:
    return str(uuid4())
