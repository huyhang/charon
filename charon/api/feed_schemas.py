"""HTTP shapes for feeds and their items."""

from datetime import datetime, timedelta

from pydantic import BaseModel, Field, field_validator

from charon.domain.feeds import Feed, FeedFailure, mask_url
from charon.domain.models import Actor, JobStatus
from charon.domain.times import to_utc
from charon.hints import hint_for
from charon.ports.stores import UnreadCounts
from charon.services.feed_inbox import InboxItem, InboxPage, MatchFilter
from charon.services.feed_service import FeedPreview
from charon.services.rule_service import Preview


class ProblemView(BaseModel):
    code: str
    message: str
    hint: str | None = Field(description="What to do about it, in plain language.")

    @classmethod
    def of(cls, code: str, message: str) -> "ProblemView":
        return cls(code=code, message=message, hint=hint_for(code))


class FeedView(BaseModel):
    id: str
    name: str
    url: str = Field(
        description="The address with passkeys and tokens masked. "
        "Admins can read it whole at GET /feeds/{id}/url."
    )
    enabled: bool
    refresh_minutes: int
    auto_download: bool
    title: str | None = Field(description="The feed's own title, from its last fetch.")
    created_at: datetime
    updated_at: datetime
    created_by: Actor | None
    updated_by: Actor | None
    last_checked_at: datetime | None
    next_check_at: datetime | None = Field(description="Null while the feed is disabled.")
    last_error: ProblemView | None = Field(description="Null while the feed is healthy.")

    @classmethod
    def from_feed(cls, feed: Feed) -> "FeedView":
        return cls(
            url=mask_url(feed.url),
            next_check_at=_next_check(feed),
            last_error=_problem(feed.last_error),
            **feed.model_dump(
                include={
                    "id",
                    "name",
                    "enabled",
                    "refresh_minutes",
                    "auto_download",
                    "title",
                    "created_at",
                    "updated_at",
                    "created_by",
                    "updated_by",
                    "last_checked_at",
                }
            ),
        )


class FeedUrlView(BaseModel):
    url: str


class FeedPreviewRequest(BaseModel):
    url: str = Field(max_length=2000)


class FeedRefView(BaseModel):
    id: str
    name: str


class ItemMatchView(BaseModel):
    rule_id: str
    rule_name: str
    new_name: str
    final_path: str


class ItemJobView(BaseModel):
    id: str
    status: JobStatus
    percent: float
    error_code: str | None


class FeedItemView(BaseModel):
    info_hash: str
    name: str = Field(description="What rules match: the magnet's name, else the item's title.")
    title: str
    magnet: str
    size_bytes: int | None
    published_at: datetime
    published_estimated: bool = Field(
        description="True when the feed gave no date and published_at is when Charon first saw it."
    )
    first_seen_at: datetime
    seen: bool
    feeds: list[FeedRefView] = Field(description="Every subscribed feed that lists it.")
    match: ItemMatchView | None = Field(description="The rule that would file it, if any.")
    match_error: ProblemView | None = Field(
        description="Set when the matching rule can't be applied to this name."
    )
    job: ItemJobView | None = Field(
        description="The newest download of this torrent, however it was added."
    )
    auto_downloaded: bool
    auto_error: str | None = Field(description="Why auto-download couldn't start it, if it tried.")

    @classmethod
    def from_inbox(cls, entry: InboxItem) -> "FeedItemView":
        item, job, error = entry.item, entry.job, entry.match.error
        return cls(
            seen=item.seen_at is not None,
            feeds=[FeedRefView(id=f.id, name=f.name) for f in entry.feeds],
            match=_match(entry.match.preview),
            match_error=ProblemView.of(error.code, error.message) if error else None,
            job=ItemJobView(
                id=job.id,
                status=job.status,
                percent=job.progress.percent,
                error_code=job.error.code if job.error else None,
            )
            if job
            else None,
            **item.model_dump(exclude={"seen_at", "job_id", "feed_ids"}),
        )


class FeedItemListView(BaseModel):
    items: list[FeedItemView]
    next_cursor: str | None

    @classmethod
    def from_page(cls, page: InboxPage) -> "FeedItemListView":
        return cls(
            items=[FeedItemView.from_inbox(i) for i in page.items], next_cursor=page.next_cursor
        )


class FeedPreviewView(BaseModel):
    title: str | None
    item_count: int = Field(description="Items with a magnet link.")
    skipped_count: int = Field(description="Items without one, which Charon ignores.")
    newest_published_at: datetime | None
    items: list[FeedItemView] = Field(description="The newest few, checked against the rules.")

    @classmethod
    def from_preview(cls, preview: FeedPreview) -> "FeedPreviewView":
        return cls(
            title=preview.title,
            item_count=preview.item_count,
            skipped_count=preview.skipped_count,
            newest_published_at=preview.newest_published_at,
            items=[FeedItemView.from_inbox(i) for i in preview.items],
        )


class MarkSeenRequest(BaseModel):
    info_hashes: list[str] = Field(
        min_length=1,
        max_length=1000,
        description="The items to mark seen, e.g. the ones a list showed.",
    )


class MarkAllSeenRequest(BaseModel):
    up_to: datetime = Field(
        description="Only items Charon first saw at or before this time, e.g. when the list "
        "was loaded, so items that arrived since stay new."
    )
    feed_id: str | None = Field(default=None, description="Only this feed's items.")
    match: MatchFilter = Field(default=MatchFilter.ALL, description="Only items in this view.")
    q: str | None = Field(default=None, max_length=200, description="Only names containing this.")

    @field_validator("up_to")
    @classmethod
    def _check_up_to(cls, value: datetime) -> datetime:
        return to_utc(value)


class MarkSeenView(BaseModel):
    marked: int


class FeedSummaryView(BaseModel):
    unread: int = Field(description="Unseen items across every feed, each counted once.")
    feeds: dict[str, int] = Field(description="Unseen items per feed id.")

    @classmethod
    def from_counts(cls, counts: UnreadCounts) -> "FeedSummaryView":
        return cls(unread=counts.total, feeds=counts.by_feed)


class DownloadItemRequest(BaseModel):
    rule_id: str | None = Field(default=None, description="Force this rule.")


def _next_check(feed: Feed) -> datetime | None:
    if not feed.enabled:
        return None
    if feed.last_checked_at is None:
        return feed.created_at
    return feed.last_checked_at + timedelta(minutes=feed.refresh_minutes)


def _problem(failure: FeedFailure | None) -> ProblemView | None:
    return ProblemView.of(failure.code, failure.message) if failure else None


def _match(preview: Preview | None) -> ItemMatchView | None:
    if preview is None or preview.rule is None or preview.final_path is None:
        return None
    return ItemMatchView(
        rule_id=preview.rule.id,
        rule_name=preview.rule.name,
        new_name=preview.new_name,
        final_path=preview.final_path,
    )
