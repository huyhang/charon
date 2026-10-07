from datetime import timedelta

import pytest

from charon.adapters.sqlite.database import Database
from charon.adapters.sqlite.feed_item_store import SqliteFeedItemStore
from charon.adapters.sqlite.feed_store import SqliteFeedStore
from charon.ports.stores import ItemFilter, UnreadCounts
from tests.unit.fakes import T0, InMemoryFeedItemStore
from tests.unit.feed_samples import hash_for, make_feed, make_item


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "charon.db")
    yield database
    database.close()


def at(minutes: int):
    return T0 + timedelta(minutes=minutes)


def test_feed_store_crud(db) -> None:
    store = SqliteFeedStore(db)
    store.add(make_feed(id="b", created_at=at(1)))
    store.add(make_feed(id="a"))
    assert [f.id for f in store.list()] == ["a", "b"]
    assert store.update_fields("a", {"name": "Renamed"}).name == "Renamed"
    assert store.get("a").name == "Renamed"
    assert store.update_fields("zzz", {"name": "Renamed"}) is None
    assert store.delete("a") is True
    assert store.delete("a") is False
    assert store.get("a") is None


# The in-memory fake must behave like the real store, so both run the same checks.
@pytest.fixture(params=["sqlite", "memory"])
def items(request, db):
    return SqliteFeedItemStore(db) if request.param == "sqlite" else InMemoryFeedItemStore()


def seed(items) -> None:
    items.save(
        [
            make_item(1, name="Show.A.mkv", published_at=at(3), first_seen_at=at(0)),
            make_item(2, name="100%_done.mkv", published_at=at(2), first_seen_at=at(1), seen_at=T0),
            make_item(3, name="Show.B.mkv", published_at=at(1), first_seen_at=at(2), job_id="j"),
        ]
    )
    items.link("feed-1", [hash_for(1), hash_for(2)], T0)
    items.link("feed-2", [hash_for(2), hash_for(3)], T0)
    # Feed 2 lists item 1 later on; listing it again doesn't move its first listing.
    items.link("feed-2", [hash_for(1)], at(5))
    items.link("feed-2", [hash_for(1)], at(9))


def test_get_many_includes_the_feeds_listing_each_item(items) -> None:
    seed(items)
    found = items.get_many([hash_for(2), hash_for(3), "missing"])
    assert {h: i.feed_ids for h, i in found.items()} == {
        hash_for(2): ["feed-1", "feed-2"],
        hash_for(3): ["feed-2"],
    }


@pytest.mark.parametrize(
    ("filter", "expected"),
    [
        (ItemFilter(), [1, 2, 3]),
        (ItemFilter(feed_id="feed-2"), [1, 2, 3]),
        (ItemFilter(feed_id="feed-1"), [1, 2]),
        (ItemFilter(unseen_only=True), [1, 3]),
        (ItemFilter(search="show"), [1, 3]),
        (ItemFilter(search="SHOW.a"), [1]),
        (ItemFilter(search="100%_"), [2]),
        (ItemFilter(search="_"), [2]),
        (ItemFilter(feed_id="feed-2", listed_after=at(0)), [1]),
        (ItemFilter(feed_id="feed-1", listed_after=at(0)), []),
        (ItemFilter(listed_after=at(0)), [1]),
        (ItemFilter(first_seen_until=at(1)), [1, 2]),
        (ItemFilter(without_job=True), [1, 2]),
    ],
    ids=[
        "all",
        "feed",
        "other-feed",
        "unseen",
        "search",
        "search-any-case",
        "literal-wildcards",
        "underscore",
        "listed-by-feed-after",
        "listed-by-other-feed-after",
        "listed-by-any-feed-after",
        "first-seen-until",
        "no-job",
    ],
)
def test_list_filters_newest_first(items, filter: ItemFilter, expected: list[int]) -> None:
    seed(items)
    assert [i.info_hash for i in items.list(filter, None, 10)] == [hash_for(n) for n in expected]


def test_list_resumes_after_a_cursor(items) -> None:
    seed(items)
    first = items.list(ItemFilter(), None, 2)
    after = (first[-1].published_at, first[-1].info_hash)
    assert [i.info_hash for i in items.list(ItemFilter(), after, 2)] == [hash_for(3)]


def test_search_ignores_case_beyond_ascii(items) -> None:
    items.save([make_item(1, name="Ärzte.Live.mkv")])
    items.link("feed-1", [hash_for(1)], T0)
    assert [i.info_hash for i in items.list(ItemFilter(search="ärzte"), None, 10)] == [hash_for(1)]


def test_save_adds_new_items_but_leaves_stored_ones(items) -> None:
    seed(items)
    items.save([make_item(1, name="Renamed", published_at=at(3), first_seen_at=at(0))])
    item = items.get_many([hash_for(1)])[hash_for(1)]
    assert (item.name, item.feed_ids) == ("Show.A.mkv", ["feed-1", "feed-2"])


def test_update_changes_only_the_given_fields(items) -> None:
    seed(items)
    updated = items.update(hash_for(1), {"job_id": "job-9"})
    assert (updated.job_id, updated.name, updated.feed_ids) == (
        "job-9",
        "Show.A.mkv",
        ["feed-1", "feed-2"],
    )
    assert items.list(ItemFilter(without_job=True), None, 10)[0].info_hash == hash_for(2)
    assert items.update("missing", {"job_id": "job-9"}) is None


def test_mark_seen_marks_only_the_given_unseen_items(items) -> None:
    seed(items)
    assert items.unread_counts() == UnreadCounts(total=2, by_feed={"feed-1": 1, "feed-2": 2})
    assert items.mark_seen([hash_for(2), hash_for(3), "missing"], at(9)) == 1
    assert items.get_many([hash_for(3)])[hash_for(3)].seen_at == at(9)
    assert items.get_many([hash_for(2)])[hash_for(2)].seen_at == T0
    assert items.unread_counts() == UnreadCounts(total=1, by_feed={"feed-1": 1, "feed-2": 1})


def test_unlink_feed_forgets_items_no_other_feed_lists(items) -> None:
    seed(items)
    items.unlink_feed("feed-2")
    assert sorted(items.get_many([hash_for(n) for n in (1, 2, 3)])) == [hash_for(1), hash_for(2)]


@pytest.mark.parametrize(
    ("cutoffs", "kept"),
    [
        ({"feed-1": at(15), "feed-2": at(15)}, [1, 2]),
        ({"feed-1": at(15)}, [1, 2, 3]),
        ({"feed-1": at(15), "feed-2": at(10)}, [1, 2, 3]),
    ],
    ids=["both-feeds-pruned", "feed-left-out-keeps-its-items", "earlier-cutoff-keeps-more"],
)
def test_touch_and_prune_keep_items_still_listed(items, cutoffs, kept: list[int]) -> None:
    seed(items)
    items.link("feed-2", [hash_for(3)], at(10))
    items.touch("feed-1", T0, at(20))
    items.prune(cutoffs)
    found = sorted(items.get_many([hash_for(n) for n in (1, 2, 3)]))
    assert found == [hash_for(n) for n in kept]
