import base64
from datetime import timedelta

import pytest

from charon.domain.events import EventType
from charon.domain.models import Actor, JobStatus, RuleSpec
from charon.errors import InvalidInputError, NotFoundError
from charon.services import feed_inbox
from charon.services.feed_inbox import (
    InboxQuery,
    Match,
    MatchFilter,
    decode_item_cursor,
    encode_item_cursor,
)
from charon.services.rule_service import Preview
from tests.unit.fakes import T0, make_job, make_rule
from tests.unit.feed_harness import SHOW_RULE, FeedHarness
from tests.unit.feed_samples import hash_for, make_feed, make_item

PHONE = Actor(name="phone", key_id="key-1")


def at(minutes: int):
    return T0 + timedelta(minutes=minutes)


def seeded(h: FeedHarness | None = None) -> FeedHarness:
    """Items 1-4, newest first by number: 1, 3 match the rule; 2, 4 don't."""
    h = h or FeedHarness(
        feeds=[make_feed(id="feed-1", name="TV"), make_feed(id="feed-2", name="Anime")]
    )
    items = [
        make_item(1, published_at=at(4)),
        make_item(2, name="Other.2.mkv", published_at=at(3), seen_at=T0),
        make_item(3, published_at=at(2)),
        make_item(4, name="Other.4.mkv", published_at=at(1)),
    ]
    h.items.save(items)
    h.items.link("feed-1", [hash_for(1), hash_for(2), hash_for(3)], T0)
    h.items.link("feed-2", [hash_for(3), hash_for(4)], T0)
    return h


def names(page) -> list[str]:
    return [entry.item.info_hash[-1] for entry in page.items]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (InboxQuery(), ["1", "2", "3", "4"]),
        (InboxQuery(match=MatchFilter.MATCHED), ["1", "3"]),
        (InboxQuery(match=MatchFilter.UNMATCHED), ["2", "4"]),
        (InboxQuery(feed_id="feed-2"), ["3", "4"]),
        (InboxQuery(unseen_only=True), ["1", "3", "4"]),
        (InboxQuery(search="other"), ["2", "4"]),
        (InboxQuery(feed_id="feed-1", match=MatchFilter.UNMATCHED), ["2"]),
    ],
    ids=["all", "matched", "unmatched", "feed", "unseen", "search", "combined"],
)
def test_list_filters(query: InboxQuery, expected: list[str]) -> None:
    assert names(seeded().inbox.list(query)) == expected


@pytest.mark.parametrize("batch", [1, 2, 200])
def test_list_pages_through_match_filtered_items(monkeypatch, batch: int) -> None:
    monkeypatch.setattr(feed_inbox, "SCAN_BATCH", batch)
    h = seeded()
    query = InboxQuery(match=MatchFilter.UNMATCHED)
    first = h.inbox.list(query, limit=1)
    second = h.inbox.list(query, first.next_cursor, limit=1)
    assert (names(first), names(second), second.next_cursor) == (["2"], ["4"], None)


def test_list_annotates_match_job_and_feeds() -> None:
    h = seeded()
    h.jobs.add(make_job(id="job-7", magnet=make_item(3).magnet, status=JobStatus.DONE))
    entry = next(e for e in h.inbox.list(InboxQuery()).items if e.item.info_hash == hash_for(3))
    assert entry.match.rule.id == "tv"
    assert entry.match.preview.final_path == "/tv/Show.S01E03.mkv"
    assert entry.job.id == "job-7"
    assert [f.name for f in entry.feeds] == ["TV", "Anime"]


def test_list_reflects_rule_edits_immediately() -> None:
    h = seeded()
    assert names(h.inbox.list(InboxQuery(match=MatchFilter.MATCHED))) == ["1", "3"]
    h.rules.create(RuleSpec(name="Other", pattern="Other.*", destination="/other"))
    assert names(h.inbox.list(InboxQuery(match=MatchFilter.MATCHED))) == ["1", "2", "3", "4"]


def test_a_rule_that_breaks_on_a_name_counts_as_matched_with_an_error() -> None:
    unsafe = make_rule(pattern="Show.*", steps=[{"op": "replace", "find": "Show", "replace": "/"}])
    h = seeded(FeedHarness(unsafe))
    entry = h.inbox.list(InboxQuery(match=MatchFilter.MATCHED)).items[0]
    assert (entry.match.preview, entry.match.error.code) == (None, "unsafe_name")


@pytest.mark.parametrize(
    ("match", "wanted", "passes"),
    [
        (Match(preview=Preview(None, "x", None)), MatchFilter.UNMATCHED, True),
        (Match(preview=Preview(SHOW_RULE, "x", "/tv/x")), MatchFilter.MATCHED, True),
        (Match(error=InvalidInputError("rule_timeout", "slow")), MatchFilter.MATCHED, True),
        (Match(error=InvalidInputError("rule_timeout", "slow")), MatchFilter.UNMATCHED, False),
        (Match(preview=Preview(None, "x", None)), MatchFilter.ALL, True),
    ],
)
def test_match_passes(match: Match, wanted: MatchFilter, passes: bool) -> None:
    assert match.passes(wanted) is passes


def test_download_links_the_job_and_records_it() -> None:
    h = seeded()
    submission = h.inbox.download(hash_for(1), None, PHONE)
    item = h.items.get_many([hash_for(1)])[hash_for(1)]
    assert (submission.created, item.job_id) == (True, submission.job.id)
    assert submission.job.created_by == PHONE
    [event] = [e for e in h.events.recorded if e.type is EventType.FEED_ITEM_DOWNLOADED]
    assert event.data == {"job_id": "job-1", "name": "Show.S01E01.mkv", "auto": False}


def test_download_of_a_torrent_already_in_charon_links_the_existing_job() -> None:
    h = seeded()
    existing = h.downloads.submit(make_item(1).magnet).job
    submission = h.inbox.download(hash_for(1), None)
    assert (submission.created, submission.job.id) == (False, existing.id)
    assert h.items.get_many([hash_for(1)])[hash_for(1)].job_id == existing.id
    assert EventType.FEED_ITEM_DOWNLOADED not in h.events.types()


def test_unknown_items_are_not_found() -> None:
    h = seeded()
    for action in (lambda: h.inbox.get("nope"), lambda: h.inbox.download("nope", None)):
        with pytest.raises(NotFoundError) as exc_info:
            action()
        assert exc_info.value.code == "feed_item_not_found"


def test_mark_seen_marks_exactly_the_given_items() -> None:
    h = seeded()
    assert h.inbox.unread().total == 3
    assert h.inbox.unread().by_feed == {"feed-1": 2, "feed-2": 2}
    assert h.inbox.mark_seen([hash_for(1), hash_for(2), hash_for(4)]) == 2
    assert h.inbox.unread().by_feed == {"feed-1": 1, "feed-2": 1}


@pytest.mark.parametrize(
    ("query", "still_unseen"),
    [
        (InboxQuery(), []),
        (InboxQuery(feed_id="feed-2"), ["1"]),
        (InboxQuery(match=MatchFilter.MATCHED), ["4"]),
        (InboxQuery(match=MatchFilter.UNMATCHED), ["1", "3"]),
        (InboxQuery(search="other"), ["1", "3"]),
    ],
    ids=["everything", "one-feed", "matched-view", "unmatched-view", "search"],
)
def test_mark_all_seen_marks_only_what_the_view_shows(
    monkeypatch, query: InboxQuery, still_unseen: list[str]
) -> None:
    monkeypatch.setattr(feed_inbox, "SCAN_BATCH", 1)
    h = seeded()
    h.inbox.mark_all_seen(query, up_to=T0)
    assert names(h.inbox.list(InboxQuery(unseen_only=True))) == still_unseen


def test_mark_all_seen_leaves_items_that_arrived_later_new() -> None:
    h = seeded()
    h.items.save([make_item(9, first_seen_at=at(10))])
    h.items.link("feed-1", [hash_for(9)], at(10))
    assert h.inbox.mark_all_seen(InboxQuery(), up_to=at(5)) == 3
    assert h.inbox.unread().total == 1


@pytest.mark.parametrize(
    ("items_seen_at", "forgotten"),
    [(at(60), 3), (T0, 0), (None, 0)],
    ids=["read-lately", "unread-since-it-listed-them", "never-read"],
)
def test_prune_ages_listings_only_while_feeds_are_read(items_seen_at, forgotten: int) -> None:
    feeds = [make_feed(id=f, items_seen_at=items_seen_at) for f in ("feed-1", "feed-2")]
    h = seeded(FeedHarness(feeds=feeds))
    h.clock.advance(3600)
    h.items.link("feed-1", [hash_for(1)], h.clock())
    assert h.inbox.prune(timedelta(minutes=30)) == forgotten


@pytest.mark.parametrize(
    "garbage",
    ["!!!", base64.urlsafe_b64encode(b"0001-01-01T00:00:00+01:00|x").decode()],
    ids=["not-base64", "out-of-range-time"],
)
def test_item_cursor_round_trip_and_garbage(garbage: str) -> None:
    item = make_item(1)
    assert decode_item_cursor(encode_item_cursor(item)) == (item.published_at, item.info_hash)
    with pytest.raises(InvalidInputError):
        decode_item_cursor(garbage)
