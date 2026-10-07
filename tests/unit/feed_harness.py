"""Feed services wired with in-memory fakes."""

from charon.services.auto_downloader import AutoDownloader
from charon.services.download_service import DownloadService
from charon.services.feed_inbox import FeedInbox
from charon.services.feed_refresher import FeedRefresher
from charon.services.feed_service import FeedService
from charon.services.rule_service import RuleService
from tests.unit.fakes import (
    ALLOW_ALL,
    FakeClock,
    FakeDownloader,
    FakeFeedFetcher,
    InMemoryFeedItemStore,
    InMemoryFeedStore,
    InMemoryJobStore,
    InMemoryRuleStore,
    RecordingEventLog,
    SequentialIds,
    make_rule,
)

# Matches the sample items' names (Show.S01E01.mkv, ...).
SHOW_RULE = make_rule(id="tv", name="TV", pattern="Show.*", destination="/tv")


class FeedHarness:
    def __init__(self, *rules, feeds=()) -> None:
        self.clock = FakeClock()
        self.events = RecordingEventLog()
        self.jobs = InMemoryJobStore()
        self.downloader = FakeDownloader()
        self.rule_store = InMemoryRuleStore(rules or [SHOW_RULE])
        self.rules = RuleService(self.rule_store, ALLOW_ALL, self.events, clock=self.clock)
        self.downloads = DownloadService(
            self.jobs, self.rules, self.downloader, self.events, self.clock, SequentialIds("job")
        )
        self.fetcher = FakeFeedFetcher()
        self.feeds = InMemoryFeedStore(feeds)
        self.items = InMemoryFeedItemStore()
        self.inbox = FeedInbox(
            self.items, self.feeds, self.rules, self.downloads, self.events, self.clock
        )
        self.auto = AutoDownloader(self.items, self.rules, self.downloads, self.events)
        self.refresher = FeedRefresher(
            self.fetcher, self.feeds, self.items, self.auto, self.events, self.clock
        )
        self.service = FeedService(
            self.feeds,
            self.items,
            self.fetcher,
            self.refresher,
            self.inbox,
            self.events,
            SequentialIds("feed"),
            self.clock,
        )
