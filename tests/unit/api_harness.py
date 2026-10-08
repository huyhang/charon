"""A Charon app wired entirely with in-memory fakes, for API tests."""

from pathlib import Path, PurePosixPath

from fastapi.testclient import TestClient

from charon.adapters.tmdb.mapping import TMDB
from charon.api.app import create_app
from charon.bootstrap import METADATA_KEY_CHECKS
from charon.container import Container
from charon.domain.destinations import DestinationPolicy
from charon.services.api_key_service import ApiKeyService
from charon.services.auto_downloader import AutoDownloader
from charon.services.destination_service import DestinationService
from charon.services.download_folder import DownloadFolder
from charon.services.download_service import DownloadService
from charon.services.event_service import EventService
from charon.services.feed_inbox import FeedInbox
from charon.services.feed_refresher import FeedRefresher
from charon.services.feed_service import FeedService
from charon.services.housekeeper import Housekeeper
from charon.services.idempotency_service import IdempotencyService
from charon.services.metadata_service import MetadataService, MetadataSource
from charon.services.post_processor import PostProcessor
from charon.services.provider_keys import ProviderKeys
from charon.services.rule_service import RuleService
from charon.services.watcher import Watcher
from tests.unit.fakes import (
    ALLOW_ALL,
    FakeClock,
    FakeDownloader,
    FakeFeedFetcher,
    FakeFileOps,
    FakeTitleProvider,
    InMemoryApiKeyStore,
    InMemoryEventStore,
    InMemoryFeedItemStore,
    InMemoryFeedStore,
    InMemoryIdempotencyStore,
    InMemoryJobStore,
    InMemoryRuleStore,
    InMemorySettingsStore,
    SequentialIds,
)


class Harness:
    def __init__(
        self,
        admin_key: str | None = None,
        cors_origins: list[str] | None = None,
        ui_dir: Path | None = None,
        policy: DestinationPolicy = ALLOW_ALL,
        roots: tuple[str, ...] = ("/",),
        tmdb_key: str | None = "harness-tmdb-token-0001",
    ) -> None:
        self.jobs = InMemoryJobStore()
        self.downloader = FakeDownloader()
        self.files = FakeFileOps()
        self.clock = clock = FakeClock()
        self.api_keys = ApiKeyService(InMemoryApiKeyStore(), admin_key, clock, SequentialIds("key"))
        self.events = EventService(InMemoryEventStore(), clock)
        rules = RuleService(
            InMemoryRuleStore(), policy, self.events, new_id=SequentialIds("rule"), clock=clock
        )
        folder = DownloadFolder(self.files, PurePosixPath("/downloads"))
        processor = PostProcessor(
            self.jobs, rules, self.downloader, self.files, folder, policy, self.events, clock
        )
        self.watcher = Watcher(self.jobs, self.downloader, processor, folder, self.events, clock)
        downloads = DownloadService(
            self.jobs, rules, self.downloader, folder, self.events, clock, SequentialIds("job")
        )
        idempotency = IdempotencyService(InMemoryIdempotencyStore(), clock)
        self.fetcher = FakeFeedFetcher()
        self.feeds, self.items = InMemoryFeedStore(), InMemoryFeedItemStore()
        inbox = FeedInbox(self.items, self.feeds, rules, downloads, self.events, clock)
        auto = AutoDownloader(self.items, rules, downloads, self.events)
        refresher = FeedRefresher(self.fetcher, self.feeds, self.items, auto, self.events, clock)
        feed_service = FeedService(
            self.feeds,
            self.items,
            self.fetcher,
            refresher,
            inbox,
            self.events,
            SequentialIds("feed"),
            clock,
        )
        self.titles = FakeTitleProvider()
        # TMDB has a key from the environment unless a test takes it away (tmdb_key=None).
        self.settings = InMemorySettingsStore()
        self.metadata_keys = ProviderKeys(self.settings, {TMDB.id: tmdb_key}, METADATA_KEY_CHECKS)
        container = Container(
            download_service=downloads,
            rule_service=rules,
            api_key_service=self.api_keys,
            destination_service=DestinationService(roots, policy, self.files),
            event_service=self.events,
            idempotency_service=idempotency,
            feed_service=feed_service,
            feed_inbox=inbox,
            housekeeper=Housekeeper(self.events, idempotency, inbox),
            downloader=self.downloader,
            watcher=self.watcher,
            metadata_service=MetadataService(
                [MetadataSource(TMDB, self.titles)], self.metadata_keys
            ),
            cors_origins=cors_origins or [],
            ui_dir=ui_dir,
        )
        self.app = create_app(container)
        self.client = TestClient(self.app, base_url="http://testserver/api/v1")
