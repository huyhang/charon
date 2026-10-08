from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from charon.ports.downloader import Downloader
from charon.services.api_key_service import ApiKeyService
from charon.services.destination_service import DestinationService
from charon.services.download_service import DownloadService
from charon.services.event_service import EventService
from charon.services.feed_inbox import FeedInbox
from charon.services.feed_service import FeedService
from charon.services.housekeeper import Housekeeper
from charon.services.idempotency_service import IdempotencyService
from charon.services.metadata_service import MetadataService
from charon.services.rule_service import RuleService
from charon.services.watcher import Watcher


@dataclass
class Container:
    """Everything the HTTP layer needs, already wired together."""

    download_service: DownloadService
    rule_service: RuleService
    api_key_service: ApiKeyService
    destination_service: DestinationService
    event_service: EventService
    idempotency_service: IdempotencyService
    feed_service: FeedService
    feed_inbox: FeedInbox
    downloader: Downloader
    watcher: Watcher
    housekeeper: Housekeeper
    metadata_service: MetadataService
    poll_interval_seconds: float | None = None
    feed_poll_interval_seconds: float | None = None
    housekeeping_interval_seconds: float | None = None
    cors_origins: list[str] = field(default_factory=list)
    ui_dir: Path | None = None
    closers: list[Callable[[], None]] = field(default_factory=list)
