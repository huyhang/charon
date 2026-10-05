"""A Charon app wired entirely with in-memory fakes, for API tests."""

from pathlib import Path, PurePosixPath

from fastapi.testclient import TestClient

from charon.api.app import create_app
from charon.container import Container
from charon.domain.destinations import DestinationPolicy
from charon.services.api_key_service import ApiKeyService
from charon.services.destination_service import DestinationService
from charon.services.download_service import DownloadService
from charon.services.post_processor import PostProcessor
from charon.services.rule_service import RuleService
from charon.services.watcher import Watcher
from tests.unit.fakes import (
    ALLOW_ALL,
    FakeClock,
    FakeDownloader,
    FakeFileOps,
    InMemoryApiKeyStore,
    InMemoryJobStore,
    InMemoryRuleStore,
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
    ) -> None:
        self.jobs = InMemoryJobStore()
        self.downloader = FakeDownloader()
        self.files = FakeFileOps()
        clock = FakeClock()
        self.api_keys = ApiKeyService(InMemoryApiKeyStore(), admin_key, clock, SequentialIds("key"))
        rules = RuleService(InMemoryRuleStore(), policy, new_id=SequentialIds("rule"), clock=clock)
        processor = PostProcessor(
            self.jobs,
            rules,
            self.downloader,
            self.files,
            PurePosixPath("/downloads"),
            policy,
            clock,
        )
        self.watcher = Watcher(self.jobs, self.downloader, processor, clock)
        container = Container(
            download_service=DownloadService(
                self.jobs, rules, self.downloader, clock, SequentialIds("job")
            ),
            rule_service=rules,
            api_key_service=self.api_keys,
            destination_service=DestinationService(roots, policy, self.files),
            downloader=self.downloader,
            watcher=self.watcher,
            cors_origins=cors_origins or [],
            ui_dir=ui_dir,
        )
        self.app = create_app(container)
        self.client = TestClient(self.app, base_url="http://testserver/api/v1")
