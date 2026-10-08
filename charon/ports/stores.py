"""Persistence ports."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from charon.domain.events import Event, EventType
from charon.domain.feeds import Feed, FeedItem
from charon.domain.models import ApiKey, IdempotencyRecord, Job, JobStatus, Rule

# (created_at, id) of the last item already seen; listing resumes after it.
JobCursor = tuple[datetime, str]


class JobStore(Protocol):
    def add(self, job: Job) -> None: ...

    def get(self, job_id: str) -> Job | None: ...

    def update(self, job: Job, expected: JobStatus) -> bool:
        """Save the job only if its stored status is still `expected`."""
        ...

    def list(
        self,
        statuses: Collection[JobStatus] | None = None,
        limit: int | None = None,
        after: JobCursor | None = None,
    ) -> list[Job]:
        """Return jobs newest first."""
        ...

    def count_by_status(self) -> dict[JobStatus, int]:
        """How many jobs are in each status; statuses without jobs may be left out."""
        ...

    def latest_by_hash(self, info_hashes: Collection[str]) -> dict[str, Job]:
        """The newest job for each of `info_hashes` that has one, whatever its status."""
        ...


class RuleStore(Protocol):
    def add(self, rule: Rule) -> None: ...

    def get(self, rule_id: str) -> Rule | None: ...

    def update(self, rule: Rule, expected_version: int) -> bool:
        """Save the rule only if its stored version is still `expected_version`."""
        ...

    def update_all(self, rules: Sequence[Rule], snapshot: Mapping[str, int]) -> bool:
        """Save every rule, or none unless the stored rules are exactly `snapshot`.

        `snapshot` maps every rule id that should exist to the version it should have, so a
        rule added, deleted or edited since the snapshot was taken fails the whole call.
        """
        ...

    def delete(self, rule_id: str) -> bool: ...

    def list(self) -> list[Rule]:
        """Return rules ordered by priority, then creation time."""
        ...


class ApiKeyStore(Protocol):
    def add(self, key: ApiKey) -> None: ...

    def get(self, key_id: str) -> ApiKey | None: ...

    def find_by_hash(self, key_hash: str) -> ApiKey | None: ...

    def update(self, key: ApiKey) -> bool: ...

    def list(self) -> list[ApiKey]:
        """Return keys oldest first."""
        ...


class EventStore(Protocol):
    def append(self, event: Event) -> Event:
        """Store the event and return it with its id."""
        ...

    def list(
        self, after: int, limit: int, types: Collection[EventType] | None = None
    ) -> list[Event]:
        """Events with an id above `after`, oldest first."""
        ...

    def prune(self, before: datetime) -> int:
        """Delete events created before `before`; returns how many."""
        ...


class SettingsStore(Protocol):
    """Small named settings changed while Charon runs, e.g. a metadata provider's API key."""

    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> bool:
        """Forget the setting; False if it wasn't set."""
        ...


class IdempotencyStore(Protocol):
    def get(self, scope: str, key: str) -> IdempotencyRecord | None: ...

    def add(self, record: IdempotencyRecord) -> None: ...

    def prune(self, before: datetime) -> int:
        """Forget records created before `before`; returns how many."""
        ...


class FeedStore(Protocol):
    def add(self, feed: Feed) -> None: ...

    def get(self, feed_id: str) -> Feed | None: ...

    def update_fields(self, feed_id: str, changes: Mapping[str, object]) -> Feed | None:
        """Change only these fields, atomically, so concurrent changes to others survive.

        Returns the updated feed, or None if it doesn't exist.
        """
        ...

    def delete(self, feed_id: str) -> bool: ...

    def list(self) -> list[Feed]:
        """Return feeds oldest first."""
        ...


# (published_at, info_hash) of the last item already seen; listing resumes after it.
ItemCursor = tuple[datetime, str]


@dataclass(frozen=True)
class ItemFilter:
    feed_id: str | None = None
    unseen_only: bool = False
    # Case-insensitive text the item's name must contain.
    search: str | None = None
    # Only items first listed after this time: by the feed `feed_id` if set, else by any feed.
    listed_after: datetime | None = None
    # Only items Charon first saw (in any feed) at or before this time.
    first_seen_until: datetime | None = None
    without_job: bool = False


@dataclass(frozen=True)
class UnreadCounts:
    total: int = 0
    # Unread items per feed id; feeds without any may be left out.
    by_feed: dict[str, int] = field(default_factory=dict)


class FeedItemStore(Protocol):
    def get_many(self, info_hashes: Collection[str]) -> dict[str, FeedItem]: ...

    def save(self, items: Sequence[FeedItem]) -> None:
        """Add items not stored yet; stored ones are left as they are (see `update`).

        Which feeds list them is kept separately, by `link`.
        """
        ...

    def update(self, info_hash: str, changes: Mapping[str, object]) -> FeedItem | None:
        """Change only these fields, atomically; None if the item doesn't exist."""
        ...

    def link(self, feed_id: str, info_hashes: Collection[str], at: datetime) -> None:
        """Note that the feed listed these items at `at` (the first time, for new listings)."""
        ...

    def touch(self, feed_id: str, since: datetime, at: datetime) -> None:
        """Note that items the feed listed at or after `since` are still listed at `at`."""
        ...

    def list(self, filter: ItemFilter, after: ItemCursor | None, limit: int) -> list[FeedItem]:
        """Return items newest published first."""
        ...

    def mark_seen(self, info_hashes: Collection[str], at: datetime) -> int:
        """Mark those of these items that are unseen as seen at `at`; returns how many."""
        ...

    def unread_counts(self) -> UnreadCounts: ...

    def unlink_feed(self, feed_id: str) -> None:
        """Forget the feed's listings, and items no other feed lists."""
        ...

    def prune(self, cutoffs: Mapping[str, datetime]) -> int:
        """Forget each feed's listings last seen before its cutoff, then unlisted items.

        Feeds left out keep their listings. Returns how many items were forgotten.
        """
        ...
