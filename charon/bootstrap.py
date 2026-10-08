"""Composition root: the only place that knows about concrete adapters."""

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import httpx
from fastapi import FastAPI

from charon.adapters.download_station.client import SynologyClient
from charon.adapters.download_station.downloader import DownloadStationDownloader
from charon.adapters.http_feed_fetcher import HttpFeedFetcher, build_http_client
from charon.adapters.local_fs import LocalFileOps
from charon.adapters.sqlite.api_key_store import SqliteApiKeyStore
from charon.adapters.sqlite.database import Database
from charon.adapters.sqlite.event_store import SqliteEventStore
from charon.adapters.sqlite.feed_item_store import SqliteFeedItemStore
from charon.adapters.sqlite.feed_store import SqliteFeedStore
from charon.adapters.sqlite.idempotency_store import SqliteIdempotencyStore
from charon.adapters.sqlite.job_store import SqliteJobStore
from charon.adapters.sqlite.rule_store import SqliteRuleStore
from charon.adapters.sqlite.settings_store import SqliteSettingsStore
from charon.adapters.tmdb.mapping import TMDB
from charon.adapters.tmdb.provider import TmdbProvider, check_token
from charon.adapters.tmdb.provider import build_http_client as build_tmdb_http_client
from charon.api.app import create_app
from charon.config import Settings
from charon.container import Container
from charon.domain.destinations import DestinationPolicy
from charon.ports.downloader import Downloader
from charon.ports.stores import SettingsStore
from charon.services.api_key_service import ApiKeyService
from charon.services.auto_downloader import AutoDownloader
from charon.services.destination_service import DestinationService
from charon.services.download_service import DownloadService
from charon.services.event_service import EventService
from charon.services.feed_inbox import FeedInbox
from charon.services.feed_refresher import FeedRefresher
from charon.services.feed_service import FeedService
from charon.services.housekeeper import Housekeeper
from charon.services.idempotency_service import IdempotencyService
from charon.services.metadata_layers import CachedProvider, CachePolicy, RateLimitedProvider
from charon.services.metadata_service import MetadataService, MetadataSource
from charon.services.post_processor import PostProcessor
from charon.services.provider_keys import KeyCheck, ProviderKeys
from charon.services.rate_limiter import SlidingWindowLimiter
from charon.services.rule_service import RuleService
from charon.services.watcher import Watcher

DownloaderFactory = Callable[[Settings, list[Callable[[], None]]], Downloader]


def build_download_station(settings: Settings, closers: list[Callable[[], None]]) -> Downloader:
    http = httpx.Client(
        base_url=settings.ds_url,
        verify=settings.ds_verify_tls,
        timeout=settings.ds_timeout_seconds,
    )
    closers.append(http.close)
    client = SynologyClient(http, settings.ds_username, settings.ds_password.get_secret_value())
    return DownloadStationDownloader(client, settings.ds_destination)


DOWNLOADERS: dict[str, DownloaderFactory] = {
    "download_station": build_download_station,
}

# How often old events, idempotency keys and feed items are pruned.
HOUSEKEEPING_INTERVAL_SECONDS = 3600.0

# Charon never sends TMDB more than 40 requests in any 10 seconds. The window is padded by a
# second so that network delays can't bunch 41 of them into 10 seconds by the time they arrive.
TMDB_REQUEST_LIMIT = 40
TMDB_WINDOW_SECONDS = 10.0 + 1.0
# A search waits this long for a free slot, then fails with metadata_rate_limited.
TMDB_MAX_WAIT_SECONDS = 2.0
# However long TMDB asks Charon to hold back, at most this long.
TMDB_MAX_PAUSE_SECONDS = 60.0
# Answers are trusted for a day ("nothing found" for an hour), and stand in for up to a week
# while TMDB can't be asked. TMDB's terms allow caching for up to 6 months.
TMDB_CACHE = CachePolicy(
    fresh_seconds=24 * 3600.0, empty_fresh_seconds=3600.0, max_age_seconds=7 * 24 * 3600.0
)
TMDB_CACHE_ENTRIES = 512

MetadataFactory = Callable[[Settings, ProviderKeys, list[Callable[[], None]]], MetadataSource]


def build_tmdb(
    settings: Settings,
    keys: ProviderKeys,
    closers: list[Callable[[], None]],
    transport: httpx.BaseTransport | None = None,
) -> MetadataSource:
    """TMDB behind a cache and its request budget, using whichever token is current."""
    http = build_tmdb_http_client(settings.tmdb_url, settings.tmdb_timeout_seconds, transport)
    closers.append(http.close)
    limiter = SlidingWindowLimiter(TMDB_REQUEST_LIMIT, TMDB_WINDOW_SECONDS, TMDB_MAX_WAIT_SECONDS)
    budgeted = RateLimitedProvider(
        TmdbProvider(http, lambda: keys.get(TMDB.id), settings.tmdb_language),
        limiter,
        TMDB_WINDOW_SECONDS,
        TMDB_MAX_PAUSE_SECONDS,
    )
    return MetadataSource(TMDB, CachedProvider(budgeted, TMDB_CACHE, TMDB_CACHE_ENTRIES))


# Another provider is another factory here, plus its key's default and check below.
METADATA_PROVIDERS: list[MetadataFactory] = [build_tmdb]
METADATA_KEY_CHECKS: dict[str, KeyCheck] = {TMDB.id: check_token}


def metadata_key_defaults(settings: Settings) -> dict[str, str | None]:
    """Keys from the environment, used while none is saved in Charon."""
    token = settings.tmdb_token
    return {TMDB.id: token.get_secret_value() if token else None}


def build_metadata(
    settings: Settings,
    store: SettingsStore,
    closers: list[Callable[[], None]],
    factories: Iterable[MetadataFactory] = METADATA_PROVIDERS,
) -> MetadataService:
    keys = ProviderKeys(store, metadata_key_defaults(settings), METADATA_KEY_CHECKS)
    return MetadataService([factory(settings, keys, closers) for factory in factories], keys)


@dataclass(frozen=True)
class Feeds:
    service: FeedService
    inbox: FeedInbox


def build_feeds(
    settings: Settings,
    db: Database,
    rules: RuleService,
    downloads: DownloadService,
    events: EventService,
    closers: list[Callable[[], None]],
) -> Feeds:
    http = build_http_client(settings.feed_timeout_seconds)
    closers.append(http.close)
    fetcher = HttpFeedFetcher(http, settings.feed_max_bytes)
    feeds, items = SqliteFeedStore(db), SqliteFeedItemStore(db)
    inbox = FeedInbox(items, feeds, rules, downloads, events)
    auto = AutoDownloader(items, rules, downloads, events)
    refresher = FeedRefresher(fetcher, feeds, items, auto, events)
    return Feeds(FeedService(feeds, items, fetcher, refresher, inbox, events), inbox)


def build_container(settings: Settings) -> Container:
    closers: list[Callable[[], None]] = []
    db = Database(settings.db_path)
    closers.append(db.close)
    jobs = SqliteJobStore(db)
    downloader = DOWNLOADERS[settings.downloader](settings, closers)
    policy = build_destination_policy(settings)
    events = EventService(SqliteEventStore(db))
    rule_service = RuleService(SqliteRuleStore(db), policy, events)
    files = LocalFileOps()
    processor = PostProcessor(
        jobs,
        rule_service,
        downloader,
        files,
        PurePosixPath(settings.download_dir),
        policy,
        events,
    )
    downloads = DownloadService(jobs, rule_service, downloader, events)
    idempotency = IdempotencyService(SqliteIdempotencyStore(db))
    feeds = build_feeds(settings, db, rule_service, downloads, events, closers)
    return Container(
        download_service=downloads,
        rule_service=rule_service,
        api_key_service=ApiKeyService(SqliteApiKeyStore(db), _admin_key(settings)),
        destination_service=DestinationService(settings.rule_roots, policy, files),
        event_service=events,
        idempotency_service=idempotency,
        feed_service=feeds.service,
        feed_inbox=feeds.inbox,
        downloader=downloader,
        watcher=Watcher(jobs, downloader, processor, events),
        housekeeper=Housekeeper(events, idempotency, feeds.inbox),
        metadata_service=build_metadata(settings, SqliteSettingsStore(db), closers),
        poll_interval_seconds=settings.poll_interval_seconds,
        feed_poll_interval_seconds=settings.feed_poll_interval_seconds,
        housekeeping_interval_seconds=HOUSEKEEPING_INTERVAL_SECONDS,
        cors_origins=settings.cors_origins,
        ui_dir=settings.ui_dir,
        closers=closers,
    )


def build_destination_policy(settings: Settings) -> DestinationPolicy:
    """Roots come from config; Charon's own data and UI directories are always off-limits.

    Every directory is listed both as configured and with symlinks resolved: rules are
    checked as written when saved, and with symlinks resolved when files are moved.
    """
    protected = [settings.db_path.parent, *([settings.ui_dir] if settings.ui_dir else [])]
    return DestinationPolicy.of(
        _as_written_and_real(settings.rule_roots), _as_written_and_real(protected)
    )


def _as_written_and_real(paths: Iterable[Path]) -> list[str]:
    return [form for path in paths for form in (str(path), os.path.realpath(path))]


def _admin_key(settings: Settings) -> str | None:
    return settings.admin_api_key.get_secret_value() if settings.admin_api_key else None


def build_app(settings: Settings) -> FastAPI:
    return create_app(build_container(settings))
