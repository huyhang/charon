"""Composition root: the only place that knows about concrete adapters."""

import os
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath

import httpx
from fastapi import FastAPI

from charon.adapters.download_station.client import SynologyClient
from charon.adapters.download_station.downloader import DownloadStationDownloader
from charon.adapters.local_fs import LocalFileOps
from charon.adapters.sqlite.api_key_store import SqliteApiKeyStore
from charon.adapters.sqlite.database import Database
from charon.adapters.sqlite.job_store import SqliteJobStore
from charon.adapters.sqlite.rule_store import SqliteRuleStore
from charon.api.app import create_app
from charon.config import Settings
from charon.container import Container
from charon.domain.destinations import DestinationPolicy
from charon.ports.downloader import Downloader
from charon.services.api_key_service import ApiKeyService
from charon.services.destination_service import DestinationService
from charon.services.download_service import DownloadService
from charon.services.post_processor import PostProcessor
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


def build_container(settings: Settings) -> Container:
    closers: list[Callable[[], None]] = []
    db = Database(settings.db_path)
    closers.append(db.close)
    jobs = SqliteJobStore(db)
    downloader = DOWNLOADERS[settings.downloader](settings, closers)
    policy = build_destination_policy(settings)
    rule_service = RuleService(SqliteRuleStore(db), policy)
    files = LocalFileOps()
    processor = PostProcessor(
        jobs,
        rule_service,
        downloader,
        files,
        PurePosixPath(settings.download_dir),
        policy,
    )
    return Container(
        download_service=DownloadService(jobs, rule_service, downloader),
        rule_service=rule_service,
        api_key_service=ApiKeyService(SqliteApiKeyStore(db), _admin_key(settings)),
        destination_service=DestinationService(settings.rule_roots, policy, files),
        downloader=downloader,
        watcher=Watcher(jobs, downloader, processor),
        poll_interval_seconds=settings.poll_interval_seconds,
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
