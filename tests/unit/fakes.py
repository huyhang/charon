"""In-memory implementations of every port, for fast isolated tests."""

import itertools
import threading
import time
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from charon.domain.destinations import DestinationPolicy, normalize
from charon.domain.events import Event, EventType
from charon.domain.feeds import Feed, FeedItem
from charon.domain.models import Actor, ApiKey, IdempotencyRecord, Job, JobStatus, Rule
from charon.errors import DownloaderError, FeedError
from charon.ports.downloader import BackendTask
from charon.ports.feeds import FetchedFeed
from charon.ports.stores import ItemCursor, ItemFilter, JobCursor, UnreadCounts

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

# Permits every destination except a stand-in database directory.
ALLOW_ALL = DestinationPolicy.of(["/"], ["/data"])


class FakeClock:
    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float = 1) -> None:
        self.now += timedelta(seconds=seconds)


class SequentialIds:
    def __init__(self, prefix: str = "id") -> None:
        self._counter = itertools.count(1)
        self._prefix = prefix

    def __call__(self) -> str:
        return f"{self._prefix}-{next(self._counter)}"


class InMemoryJobStore:
    def __init__(self, jobs: Collection[Job] = ()) -> None:
        self.jobs = {job.id: job for job in jobs}

    def add(self, job: Job) -> None:
        self.jobs[job.id] = job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def update(self, job: Job, expected: JobStatus) -> bool:
        current = self.jobs.get(job.id)
        if current is None or current.status is not expected:
            return False
        self.jobs[job.id] = job
        return True

    def list(
        self,
        statuses: Collection[JobStatus] | None = None,
        limit: int | None = None,
        after: JobCursor | None = None,
    ) -> list[Job]:
        jobs = sorted(self.jobs.values(), key=lambda j: (j.created_at, j.id), reverse=True)
        jobs = [j for j in jobs if not statuses or j.status in statuses]
        if after is not None:
            jobs = [j for j in jobs if (j.created_at, j.id) < after]
        return jobs[:limit]

    def count_by_status(self) -> dict[JobStatus, int]:
        return dict(Counter(job.status for job in self.jobs.values()))

    def latest_by_hash(self, info_hashes: Collection[str]) -> dict[str, Job]:
        oldest_first = sorted(self.jobs.values(), key=lambda j: (j.created_at, j.id))
        return {j.info_hash: j for j in oldest_first if j.info_hash in info_hashes}


class InMemoryRuleStore:
    def __init__(self, rules: Collection[Rule] = ()) -> None:
        self.rules = {rule.id: rule for rule in rules}

    def add(self, rule: Rule) -> None:
        self.rules[rule.id] = rule

    def get(self, rule_id: str) -> Rule | None:
        return self.rules.get(rule_id)

    def update(self, rule: Rule, expected_version: int) -> bool:
        current = self.rules.get(rule.id)
        if current is None or current.version != expected_version:
            return False
        self.rules[rule.id] = rule
        return True

    def update_all(self, rules: Sequence[Rule], snapshot: Mapping[str, int]) -> bool:
        if {r.id: r.version for r in self.rules.values()} != dict(snapshot):
            return False
        self.rules.update({rule.id: rule for rule in rules})
        return True

    def delete(self, rule_id: str) -> bool:
        return self.rules.pop(rule_id, None) is not None

    def list(self) -> list[Rule]:
        return sorted(self.rules.values(), key=lambda r: (r.priority, r.created_at, r.id))


class InMemoryApiKeyStore:
    def __init__(self) -> None:
        self.keys: dict[str, ApiKey] = {}

    def add(self, key: ApiKey) -> None:
        self.keys[key.id] = key

    def get(self, key_id: str) -> ApiKey | None:
        return self.keys.get(key_id)

    def find_by_hash(self, key_hash: str) -> ApiKey | None:
        return next((k for k in self.keys.values() if k.key_hash == key_hash), None)

    def update(self, key: ApiKey) -> bool:
        if key.id not in self.keys:
            return False
        self.keys[key.id] = key
        return True

    def list(self) -> list[ApiKey]:
        return list(self.keys.values())


class InMemoryEventStore:
    def __init__(self) -> None:
        self.events: list[Event] = []
        # Ids keep growing after pruning, like SQLite's AUTOINCREMENT: they are cursors.
        self._last_id = 0

    def append(self, event: Event) -> Event:
        self._last_id += 1
        stored = event.model_copy(update={"id": self._last_id})
        self.events.append(stored)
        return stored

    def list(
        self, after: int, limit: int, types: Collection[EventType] | None = None
    ) -> list[Event]:
        matching = [e for e in self.events if e.id > after and (not types or e.type in types)]
        return matching[:limit]

    def prune(self, before: datetime) -> int:
        kept = [e for e in self.events if e.created_at >= before]
        pruned = len(self.events) - len(kept)
        self.events = kept
        return pruned


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], IdempotencyRecord] = {}

    def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        return self.records.get((scope, key))

    def add(self, record: IdempotencyRecord) -> None:
        self.records.setdefault((record.scope, record.key), record)

    def prune(self, before: datetime) -> int:
        old = [k for k, r in self.records.items() if r.created_at < before]
        for key in old:
            del self.records[key]
        return len(old)


@dataclass(frozen=True)
class Recorded:
    type: EventType
    subject_id: str
    actor: Actor
    data: dict[str, object]


class RecordingEventLog:
    """An EventLog that remembers what was recorded."""

    def __init__(self) -> None:
        self.recorded: list[Recorded] = []

    def record(self, type: EventType, subject_id: str, actor: Actor, **data: object) -> None:
        self.recorded.append(Recorded(type, subject_id, actor, data))

    def types(self) -> list[EventType]:
        return [r.type for r in self.recorded]


class InMemoryFeedStore:
    def __init__(self, feeds: Collection[Feed] = ()) -> None:
        self.feeds = {feed.id: feed for feed in feeds}

    def add(self, feed: Feed) -> None:
        self.feeds[feed.id] = feed

    def get(self, feed_id: str) -> Feed | None:
        return self.feeds.get(feed_id)

    def update_fields(self, feed_id: str, changes: Mapping[str, object]) -> Feed | None:
        if feed_id not in self.feeds:
            return None
        self.feeds[feed_id] = self.feeds[feed_id].model_copy(update=changes)
        return self.feeds[feed_id]

    def delete(self, feed_id: str) -> bool:
        return self.feeds.pop(feed_id, None) is not None

    def list(self) -> list[Feed]:
        return sorted(self.feeds.values(), key=lambda f: (f.created_at, f.id))


class InMemoryFeedItemStore:
    def __init__(self) -> None:
        self.items: dict[str, FeedItem] = {}
        # (info_hash, feed_id) -> when the feed last listed the item.
        self.sources: dict[tuple[str, str], datetime] = {}
        # (info_hash, feed_id) -> when the feed first listed the item.
        self.first_listed: dict[tuple[str, str], datetime] = {}

    def get_many(self, info_hashes: Collection[str]) -> dict[str, FeedItem]:
        return {h: self._with_feeds(self.items[h]) for h in info_hashes if h in self.items}

    def save(self, items: Sequence[FeedItem]) -> None:
        for item in items:
            self.items.setdefault(item.info_hash, item.model_copy(update={"feed_ids": []}))

    def update(self, info_hash: str, changes: Mapping[str, object]) -> FeedItem | None:
        if info_hash not in self.items:
            return None
        self.items[info_hash] = self.items[info_hash].model_copy(update=changes)
        return self._with_feeds(self.items[info_hash])

    def link(self, feed_id: str, info_hashes: Collection[str], at: datetime) -> None:
        for h in info_hashes:
            self.first_listed.setdefault((h, feed_id), at)
            self.sources[(h, feed_id)] = at

    def touch(self, feed_id: str, since: datetime, at: datetime) -> None:
        for (h, f), seen in list(self.sources.items()):
            if f == feed_id and seen >= since:
                self.sources[(h, f)] = at

    def list(self, filter: ItemFilter, after: ItemCursor | None, limit: int) -> list[FeedItem]:
        items = sorted(self.items.values(), key=lambda i: (i.published_at, i.info_hash))
        items = [self._with_feeds(i) for i in reversed(items) if self._passes(i, filter)]
        if after is not None:
            items = [i for i in items if (i.published_at, i.info_hash) < after]
        return items[:limit]

    def mark_seen(self, info_hashes: Collection[str], at: datetime) -> int:
        unseen = {h for h in info_hashes if h in self.items and self.items[h].seen_at is None}
        for h in unseen:
            self.update(h, {"seen_at": at})
        return len(unseen)

    def unread_counts(self) -> UnreadCounts:
        unseen = {h for h, i in self.items.items() if i.seen_at is None}
        by_feed = Counter(f for (h, f) in self.sources if h in unseen)
        return UnreadCounts(total=len(unseen), by_feed=dict(by_feed))

    def unlink_feed(self, feed_id: str) -> None:
        self._forget(lambda key, _: key[1] == feed_id)
        self._drop_orphans()

    def prune(self, cutoffs: Mapping[str, datetime]) -> int:
        self._forget(lambda key, seen: key[1] in cutoffs and seen < cutoffs[key[1]])
        return self._drop_orphans()

    def _forget(self, gone: Callable[[tuple[str, str], datetime], bool]) -> None:
        for key in [k for k, seen in self.sources.items() if gone(k, seen)]:
            del self.sources[key]
            self.first_listed.pop(key, None)

    def _drop_orphans(self) -> int:
        listed = {h for h, _ in self.sources}
        orphans = [h for h in self.items if h not in listed]
        for h in orphans:
            del self.items[h]
        return len(orphans)

    def _with_feeds(self, item: FeedItem) -> FeedItem:
        feeds = sorted(f for (h, f) in self.sources if h == item.info_hash)
        return item.model_copy(update={"feed_ids": feeds})

    def _passes(self, item: FeedItem, filter: ItemFilter) -> bool:
        feeds = {f for (h, f) in self.sources if h == item.info_hash}
        return (
            (filter.feed_id is None or filter.feed_id in feeds)
            and (not filter.unseen_only or item.seen_at is None)
            and (not filter.search or filter.search.casefold() in item.name.casefold())
            and self._listed_after(item, filter)
            and (filter.first_seen_until is None or item.first_seen_at <= filter.first_seen_until)
            and (not filter.without_job or item.job_id is None)
        )

    def _listed_after(self, item: FeedItem, filter: ItemFilter) -> bool:
        if filter.listed_after is None:
            return True
        return any(
            h == item.info_hash and (filter.feed_id in (None, f)) and at > filter.listed_after
            for (h, f), at in self.first_listed.items()
        )


class FakeFeedFetcher:
    """Serves documents by URL; unknown URLs fail as unreachable."""

    def __init__(self, documents: dict[str, bytes] | None = None) -> None:
        self.documents = documents or {}
        self.errors: dict[str, FeedError] = {}
        # (url, etag, last_modified) of every fetch.
        self.fetches: list[tuple[str, str | None, str | None]] = []
        # URLs whose next fetches answer "not modified".
        self.unchanged: set[str] = set()

    def fetch(
        self, url: str, etag: str | None = None, last_modified: str | None = None
    ) -> FetchedFeed:
        self.fetches.append((url, etag, last_modified))
        if url in self.errors:
            raise self.errors[url]
        if url in self.unchanged:
            # Like many servers, a bare "not modified" without the validators.
            return FetchedFeed(body=None)
        if url not in self.documents:
            raise FeedError("feed_unreachable", "couldn't reach the feed's server")
        return FetchedFeed(body=self.documents[url], etag='"v1"', last_modified=None)


class HeldAdds:
    """Holds a downloader's add() calls until released, counting the callers that got there.

    For races: start one call, then see whether a second can get as far as add() before the
    first finishes.
    """

    def __init__(self, downloader: "FakeDownloader") -> None:
        self._add = downloader.add
        self._released = threading.Event()
        self._guard = threading.Lock()
        self.calls = 0
        downloader.add = self._held  # type: ignore[method-assign]

    def wait_for(self, calls: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while self.calls < calls and time.monotonic() < deadline:
            time.sleep(0.005)
        return self.calls >= calls

    def release(self) -> None:
        self._released.set()

    def _held(self, magnet: str) -> str:
        with self._guard:
            self.calls += 1
        self._released.wait(5)
        return self._add(magnet)


class FakeDownloader:
    def __init__(self) -> None:
        self.tasks: dict[str, BackendTask | None] = {}
        self.added: list[str] = []
        self.removed: list[str] = []
        self.available = True
        self.fail_with: DownloaderError | None = None
        # Per-task errors raised by `get`, for exercising unexpected failures.
        self.broken: dict[str, Exception] = {}
        self._ids = SequentialIds("task")

    def add(self, magnet: str) -> str:
        self._maybe_fail()
        self.added.append(magnet)
        return self._ids()

    def get(self, task_id: str) -> BackendTask | None:
        self._maybe_fail()
        if task_id in self.broken:
            raise self.broken[task_id]
        return self.tasks.get(task_id)

    def remove(self, task_id: str) -> None:
        self._maybe_fail()
        self.removed.append(task_id)

    def is_available(self) -> bool:
        return self.available

    def _maybe_fail(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with


class FakeFileOps:
    def __init__(self, existing: Collection[str] = ()) -> None:
        self.paths = {PurePosixPath(p) for p in existing}
        self.moves: list[tuple[PurePosixPath, PurePosixPath]] = []
        self.fail_with: OSError | None = None
        # Errors raised by `exists` or `resolve`, keyed by method name.
        self.fail_on: dict[str, Exception] = {}
        self.symlinks: dict[PurePosixPath, PurePosixPath] = {}
        # Folder names inside each directory, for `list_folders`.
        self.folders: dict[PurePosixPath, list[str]] = {}

    def exists(self, path: PurePosixPath) -> bool:
        self._maybe_fail("exists")
        return path in self.paths

    def move(self, source: PurePosixPath, destination: PurePosixPath) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.paths.discard(source)
        self.paths.add(destination)
        self.moves.append((source, destination))

    def resolve(self, path: PurePosixPath) -> PurePosixPath:
        self._maybe_fail("resolve")
        path = normalize(path)
        for link, target in self.symlinks.items():
            if path == link or link in path.parents:
                return target / path.relative_to(link)
        return path

    def list_folders(self, path: PurePosixPath) -> list[str]:
        self._maybe_fail("list_folders")
        if path not in self.folders:
            raise FileNotFoundError(f"no such directory: {path}")
        return sorted(self.folders[path])

    def _maybe_fail(self, method: str) -> None:
        if method in self.fail_on:
            raise self.fail_on[method]


def make_job(**overrides: object) -> Job:
    fields: dict[str, object] = {
        "id": "job-1",
        "magnet": "magnet:?xt=urn:btih:abc",
        "backend_task_id": "task-1",
        "created_at": T0,
        "updated_at": T0,
    }
    return Job.model_validate({**fields, **overrides})


def make_rule(**overrides: object) -> Rule:
    fields: dict[str, object] = {
        "id": "rule-1",
        "name": "rule",
        "pattern": "*",
        "destination": "/library",
        "created_at": T0,
    }
    return Rule.model_validate({**fields, **overrides})
