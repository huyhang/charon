from datetime import timedelta

import pytest

from charon.domain.events import EventType
from charon.domain.feeds import AUTO_DOWNLOAD
from charon.domain.models import JobStatus
from charon.errors import DownloaderError
from tests.unit.fakes import T0
from tests.unit.feed_harness import FeedHarness
from tests.unit.feed_samples import hash_for, make_feed, make_item

SINCE = T0
NEW = T0 + timedelta(minutes=5)
AUTO_FEED = make_feed(auto_download=True, auto_download_since=SINCE)


def stored(h: FeedHarness, *items, feed_id: str = "feed-1", at=NEW) -> None:
    h.items.save(items)
    h.items.link(feed_id, [i.info_hash for i in items], at)


def test_downloads_new_items_that_match_a_rule() -> None:
    h = FeedHarness()
    stored(
        h,
        make_item(1, first_seen_at=NEW, published_at=NEW),
        make_item(2, name="Unmatched.mkv", first_seen_at=NEW, published_at=NEW),
    )
    # Listed by the feed when auto-download was turned on: the backlog, never taken.
    stored(h, make_item(3, first_seen_at=SINCE, published_at=NEW), at=SINCE)
    assert h.auto.run(AUTO_FEED) == 1
    item = h.items.get_many([hash_for(1)])[hash_for(1)]
    assert (item.job_id, item.auto_downloaded) == ("job-1", True)
    assert h.jobs.jobs["job-1"].created_by == AUTO_DOWNLOAD
    [event] = [e for e in h.events.recorded if e.type is EventType.FEED_ITEM_DOWNLOADED]
    assert (event.subject_id, event.actor, event.data["auto"]) == (hash_for(1), AUTO_DOWNLOAD, True)


def test_does_nothing_for_feeds_without_auto_download() -> None:
    h = FeedHarness()
    stored(h, make_item(1, first_seen_at=NEW, published_at=NEW))
    assert h.auto.run(make_feed()) == 0
    assert h.downloader.added == []


def test_does_nothing_for_paused_feeds() -> None:
    h = FeedHarness()
    stored(h, make_item(1, first_seen_at=NEW, published_at=NEW))
    assert h.auto.run(AUTO_FEED.model_copy(update={"enabled": False})) == 0
    assert h.downloader.added == []


def test_ignores_other_feeds_items() -> None:
    h = FeedHarness()
    stored(h, make_item(1, first_seen_at=NEW, published_at=NEW), feed_id="other")
    assert h.auto.run(AUTO_FEED) == 0


def test_takes_an_item_new_to_this_feed_that_another_feed_listed_first() -> None:
    h = FeedHarness()
    item = make_item(1, first_seen_at=SINCE, published_at=SINCE)
    stored(h, item, feed_id="other", at=SINCE)
    stored(h, item, at=NEW)
    assert h.auto.run(AUTO_FEED) == 1


@pytest.mark.parametrize("status", [JobStatus.CANCELLED, JobStatus.FAILED])
def test_never_takes_a_torrent_again_once_it_was_in_charon(status: JobStatus) -> None:
    h = FeedHarness()
    item = make_item(1, first_seen_at=NEW, published_at=NEW)
    job = h.downloads.submit(item.magnet).job
    h.jobs.jobs[job.id] = job.model_copy(update={"status": status})
    stored(h, item)
    assert h.auto.run(AUTO_FEED) == 0
    assert len(h.downloader.added) == 1
    assert h.items.get_many([hash_for(1)])[hash_for(1)].job_id == job.id


def test_an_item_that_cant_be_submitted_doesnt_stop_the_others() -> None:
    h = FeedHarness()
    broken = make_item(1, magnet="not-a-magnet", first_seen_at=NEW, published_at=NEW)
    stored(h, broken, make_item(2, first_seen_at=NEW, published_at=NEW))
    assert h.auto.run(AUTO_FEED) == 1
    found = h.items.get_many([hash_for(1), hash_for(2)])
    assert found[hash_for(1)].auto_error.startswith("magnet link must start with")
    assert found[hash_for(2)].job_id == "job-1"


def test_links_a_torrent_already_in_charon_without_a_new_download() -> None:
    h = FeedHarness()
    item = make_item(1, first_seen_at=NEW, published_at=NEW)
    h.downloads.submit(item.magnet)
    stored(h, item)
    assert h.auto.run(AUTO_FEED) == 0
    linked = h.items.get_many([hash_for(1)])[hash_for(1)]
    assert (linked.job_id, linked.auto_downloaded, len(h.downloader.added)) == ("job-1", False, 1)


def test_remembers_why_a_download_couldnt_start_and_retries_next_time() -> None:
    h = FeedHarness()
    stored(h, make_item(1, first_seen_at=NEW, published_at=NEW))
    h.downloader.fail_with = DownloaderError("NAS offline")
    assert h.auto.run(AUTO_FEED) == 0
    assert h.items.get_many([hash_for(1)])[hash_for(1)].auto_error == "NAS offline"
    h.downloader.fail_with = None
    assert h.auto.run(AUTO_FEED) == 1
    item = h.items.get_many([hash_for(1)])[hash_for(1)]
    assert (item.auto_error, item.job_id) == (None, "job-1")


def test_skips_items_whose_rule_cant_apply() -> None:
    h = FeedHarness()
    broken = h.rule_store.rules["tv"].model_copy(update={"destination": "/data/x"})
    h.rule_store.rules["tv"] = broken
    stored(h, make_item(1, first_seen_at=NEW, published_at=NEW))
    assert h.auto.run(AUTO_FEED) == 0
