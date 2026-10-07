"""Feeds of magnet links and the items they list. Pure data and logic, no I/O."""

import re
from datetime import datetime, timedelta
from urllib.parse import SplitResult, parse_qsl, quote, urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator

from charon.domain.models import Actor

# Credited with downloads that a feed's auto-download starts.
AUTO_DOWNLOAD = Actor(name="auto-download")

MASK = "••••"
# Path segments that are probably passkeys or tokens: unbroken runs of 8 or more mixing letters
# and digits, or UUIDs. Readable segments such as "latest-1080p" are left alone.
_TOKEN = re.compile(
    r"^(?:(?=.*\d)(?=.*[A-Za-z])[A-Za-z0-9]{8,}"
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)


_DEFAULT_PORTS = {"http": "80", "https": "443"}
# Auto-download still takes an item whose publication date is up to this long before it was
# turned on: feeds often list an item a while after the date it gives.
PUBLISHED_GRACE = timedelta(days=1)


def check_feed_url(url: str) -> str:
    """The URL, trimmed, if it is a usable http(s) address. Raises ValueError otherwise."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("must be an http:// or https:// address")
    _check_host(parts)
    return url


def feed_url_key(url: str) -> str:
    """What two addresses of the same feed have in common: the scheme and host in lower case,
    no default port and no fragment."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    userinfo, at, host = parts.netloc.rpartition("@")
    host = host.lower().removesuffix(f":{_DEFAULT_PORTS.get(scheme)}")
    return urlunsplit((scheme, f"{userinfo}{at}{host}", parts.path or "/", parts.query, ""))


def mask_url(url: str) -> str:
    """The URL with anything that looks secret (passkeys, tokens, passwords) masked.

    Keeps the scheme, host, port and ordinary path, so people can still tell feeds apart.
    """
    parts = urlsplit(url)
    userinfo, _, host = parts.netloc.rpartition("@")
    netloc = f"{MASK}@{host}" if userinfo else host
    path = "/".join(_mask_segment(segment) for segment in parts.path.split("/"))
    return urlunsplit((parts.scheme, netloc, path, _mask_pairs(parts.query, "&"), ""))


def feed_host(url: str) -> str:
    """Only the host, for messages and logs that must not leak the rest of the URL."""
    return urlsplit(url).hostname or "the feed's server"


def _check_host(parts: SplitResult) -> None:
    try:
        if parts.port == 0:
            raise ValueError("port 0")
        # Round-trips through IDNA so empty, overlong or bad punycode labels are caught here.
        (parts.hostname or "").encode("idna").decode("idna")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("has an invalid host name or port") from exc


def _mask_segment(segment: str) -> str:
    """A path segment with tokens masked, including `;name=value` parameters."""
    name, semicolon, params = segment.partition(";")
    masked = MASK if _TOKEN.match(name) else name
    return f"{masked}{semicolon}{_mask_pairs(params, ';')}"


def _mask_pairs(text: str, separator: str) -> str:
    pairs = parse_qsl(text, keep_blank_values=True, separator=separator)
    return separator.join(f"{quote(key)}={MASK if value else ''}" for key, value in pairs)


class FeedFailure(BaseModel):
    code: str
    message: str


class FeedSettings(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    refresh_minutes: int = Field(default=15, ge=5, le=1440)
    auto_download: bool = Field(
        default=False,
        description="Download items that match a rule, if they appear after this is turned on.",
    )


class FeedSpec(FeedSettings):
    """A feed as supplied by a client."""

    url: str = Field(
        max_length=2000,
        description="The RSS address. It may hold a passkey, so Charon treats it as a secret.",
    )

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        return check_feed_url(value)


class FeedUpdate(FeedSettings):
    url: str | None = Field(
        default=None, max_length=2000, description="A new address (admins only); omit to keep it."
    )

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        return check_feed_url(value) if value is not None else None


class Feed(FeedSpec):
    id: str
    created_at: datetime
    updated_at: datetime
    created_by: Actor | None = None
    updated_by: Actor | None = None
    # The channel's own title, from the last successful fetch.
    title: str | None = None
    # When auto-download was turned on; only items first seen after it are downloaded.
    auto_download_since: datetime | None = None
    last_checked_at: datetime | None = None
    last_error: FeedFailure | None = None
    # HTTP cache validators, so an unchanged feed isn't downloaded again.
    etag: str | None = None
    last_modified: str | None = None
    # When the items of the last fetched content were last confirmed to be in the feed.
    items_seen_at: datetime | None = None

    def is_due(self, now: datetime) -> bool:
        if not self.enabled:
            return False
        if self.last_checked_at is None:
            return True
        return now >= self.last_checked_at + timedelta(minutes=self.refresh_minutes)


class FeedItem(BaseModel):
    """One torrent listed by one or more feeds, identified by its info hash."""

    info_hash: str
    name: str = Field(description="What rules match: the magnet's name, else the item's title.")
    title: str
    magnet: str
    size_bytes: int | None = None
    published_at: datetime
    # True when the feed gave no date and `published_at` is when Charon first saw it.
    published_estimated: bool = False
    first_seen_at: datetime
    seen_at: datetime | None = None
    job_id: str | None = None
    auto_downloaded: bool = False
    auto_error: str | None = None
    # Every feed that lists it. Kept by the store, not part of the item's own data.
    feed_ids: list[str] = Field(default_factory=list)

    def date_changes(self, other: "FeedItem") -> dict[str, object] | None:
        """How to update this item from another listing of it, or None if nothing changes.

        The earliest real publication date wins, whichever feed it came from.
        """
        if other.published_estimated:
            return None
        if not self.published_estimated and self.published_at <= other.published_at:
            return None
        return {"published_at": other.published_at, "published_estimated": False}


def is_auto_download_candidate(feed: Feed, item: FeedItem) -> bool:
    """Whether auto-download may take an item the feed first listed after it was turned on.

    The feed must be enabled, the item not downloaded yet, and its publication date (if the
    feed gave one) no older than PUBLISHED_GRACE before auto-download was turned on, so an old
    release the feed lists again isn't taken. Callers pick items by when the feed first listed
    them; this checks the rest.
    """
    since = feed.auto_download_since
    if not (feed.enabled and feed.auto_download) or since is None or item.job_id is not None:
        return False
    return item.published_estimated or item.published_at >= since - PUBLISHED_GRACE
