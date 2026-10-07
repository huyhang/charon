"""Downloads a feed's new items that match a rule, for feeds that opted in."""

import logging

from charon.domain.events import EventType
from charon.domain.feeds import AUTO_DOWNLOAD, Feed, FeedItem, is_auto_download_candidate
from charon.domain.models import Job
from charon.errors import DownloaderError, InvalidInputError
from charon.ports.events import EventLog
from charon.ports.stores import FeedItemStore, ItemFilter
from charon.services.download_service import DownloadService
from charon.services.feed_inbox import match_with
from charon.services.rule_service import RuleService

log = logging.getLogger(__name__)

# More than any feed lists at once, so nothing new is left behind.
MAX_CANDIDATES = 1000


class AutoDownloader:
    def __init__(
        self,
        items: FeedItemStore,
        rules: RuleService,
        downloads: DownloadService,
        events: EventLog,
    ) -> None:
        self._items = items
        self._rules = rules
        self._downloads = downloads
        self._events = events

    def run(self, feed: Feed) -> int:
        """Download the feed's eligible items; returns how many downloads it started.

        A torrent that is or was in Charon (even cancelled or failed) is never taken again: it
        is linked to its job instead. Items whose download couldn't start keep the reason and
        are tried again next time, without stopping the others.
        """
        candidates = self._candidates(feed)
        if not candidates:
            return 0
        known = self._downloads.latest_by_hash([item.info_hash for item in candidates])
        matcher = self._rules.matcher()
        started = 0
        for item in candidates:
            if item.info_hash in known:
                self._link(item, known[item.info_hash])
            elif match_with(matcher, item.name).rule is not None:
                started += self._grab(item)
        return started

    def _candidates(self, feed: Feed) -> list[FeedItem]:
        since = feed.auto_download_since
        if not (feed.enabled and feed.auto_download) or since is None:
            return []
        filter = ItemFilter(feed_id=feed.id, listed_after=since, without_job=True)
        items = self._items.list(filter, None, MAX_CANDIDATES)
        return [item for item in items if is_auto_download_candidate(feed, item)]

    def _link(self, item: FeedItem, job: Job) -> None:
        self._items.update(item.info_hash, {"job_id": job.id})

    def _grab(self, item: FeedItem) -> bool:
        try:
            submission = self._downloads.submit(item.magnet, actor=AUTO_DOWNLOAD)
        except (DownloaderError, InvalidInputError) as exc:
            log.warning("auto-download of %s failed: %s", item.info_hash, exc.message)
            self._items.update(item.info_hash, {"auto_error": exc.message})
            return False
        job = submission.job
        update = {"job_id": job.id, "auto_downloaded": submission.created, "auto_error": None}
        self._items.update(item.info_hash, update)
        if submission.created:
            self._events.record(
                EventType.FEED_ITEM_DOWNLOADED,
                item.info_hash,
                AUTO_DOWNLOAD,
                job_id=job.id,
                name=item.name,
                auto=True,
            )
        return submission.created
