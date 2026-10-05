from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from charon.ports.downloader import Downloader
from charon.services.api_key_service import ApiKeyService
from charon.services.destination_service import DestinationService
from charon.services.download_service import DownloadService
from charon.services.rule_service import RuleService
from charon.services.watcher import Watcher


@dataclass
class Container:
    """Everything the HTTP layer needs, already wired together."""

    download_service: DownloadService
    rule_service: RuleService
    api_key_service: ApiKeyService
    destination_service: DestinationService
    downloader: Downloader
    watcher: Watcher
    poll_interval_seconds: float | None = None
    cors_origins: list[str] = field(default_factory=list)
    ui_dir: Path | None = None
    closers: list[Callable[[], None]] = field(default_factory=list)
