from datetime import UTC, datetime, timedelta, timezone

import pytest

from charon.domain.rss import NotRssError, parse_date, parse_feed, parse_size
from tests.unit.fakes import T0
from tests.unit.feed_samples import hash_for, magnet, rss, rss_item


def test_parses_title_items_and_skips_non_magnets() -> None:
    document = rss(
        rss_item("Show S01E01", magnet(1, "Show.S01E01.mkv"), T0),
        rss_item("A torrent file", "https://t.example/1.torrent", T0),
        rss_item("Show S01E02", magnet(2), T0 + timedelta(hours=1)),
        title="My tracker",
    )
    feed = parse_feed(document)
    assert (feed.title, feed.skipped) == ("My tracker", 1)
    first, second = feed.items
    assert (first.info_hash, first.title, first.name, first.published_at) == (
        hash_for(1),
        "Show S01E01",
        "Show.S01E01.mkv",
        T0,
    )
    assert (second.name, second.title) == ("Show S01E02", "Show S01E02")


@pytest.mark.parametrize(
    ("extra", "link", "expected"),
    [
        (
            f'<enclosure url="{magnet(7)}" length="123" type="application/x-bittorrent"/>',
            "https://x",
            hash_for(7),
        ),
        (f"<guid>{magnet(8)}</guid>", "https://x", hash_for(8)),
        ("", "magnet:?xt=urn:btih:nothash", None),
    ],
    ids=["enclosure", "guid", "magnet-without-hash"],
)
def test_finds_the_magnet_in_link_enclosure_or_guid(extra: str, link: str, expected) -> None:
    feed = parse_feed(rss(rss_item("x", link, extra=extra)))
    assert [i.info_hash for i in feed.items] == ([expected] if expected else [])


@pytest.mark.parametrize(
    ("extra", "link", "size"),
    [
        (f'<enclosure url="{magnet(1)}" length="2048"/>', "https://x", 2048),
        ("", magnet(1) + "&xl=4096", 4096),
        (
            "<nyaa:size xmlns:nyaa='https://nyaa.si/xmlns/nyaa'>1.5 GiB</nyaa:size>",
            magnet(1),
            1610612736,
        ),
        ('<enclosure url="https://x" length="0"/>', magnet(1), None),
        ('<enclosure url="https://x" length="²"/>', magnet(1) + "&xl=²", None),
    ],
    ids=["enclosure-length", "magnet-xl", "namespaced-size", "zero-length", "non-ascii-digits"],
)
def test_reads_the_size_from_the_best_source(extra: str, link: str, size) -> None:
    [item] = parse_feed(rss(rss_item("x", link, extra=extra))).items
    assert item.size_bytes == size


def test_upper_case_magnets_are_read_and_normalized() -> None:
    [item] = parse_feed(rss(rss_item("x", magnet(3).replace("magnet:?", "MAGNET:?")))).items
    assert (item.info_hash, item.magnet) == (hash_for(3), magnet(3))


def test_items_without_a_date_have_none() -> None:
    [item] = parse_feed(rss(rss_item("x", magnet(1)))).items
    assert item.published_at is None


def test_reads_dublin_core_dates() -> None:
    extra = "<dc:date xmlns:dc='http://purl.org/dc/elements/1.1/'>2026-10-01T12:00:00Z</dc:date>"
    [item] = parse_feed(rss(rss_item("x", magnet(1), extra=extra))).items
    assert item.published_at == T0


def test_reads_rss_1_rdf_feeds() -> None:
    document = (
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns="http://purl.org/rss/1.0/"><channel><title>RDF</title></channel>'
        f"<item><title>x</title><link>{magnet(3).replace('&', '&amp;')}</link></item></rdf:RDF>"
    ).encode()
    feed = parse_feed(document)
    assert (feed.title, [i.info_hash for i in feed.items]) == ("RDF", [hash_for(3)])


@pytest.mark.parametrize(
    "document",
    [
        b"not xml at all",
        b"<html><body>Login</body></html>",
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]><rss>&lol;</rss>',
        '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE x [<!ENTITY a "b">]><rss/>'.encode(
            "utf-16"
        ),
    ],
    ids=["garbage", "html", "entities", "utf16-entities"],
)
def test_rejects_documents_that_arent_safe_rss(document: bytes) -> None:
    with pytest.raises(NotRssError):
        parse_feed(document)


def test_empty_channel_has_no_items() -> None:
    feed = parse_feed(rss())
    assert (feed.items, feed.skipped) == ([], 0)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("700 MB", 700_000_000),
        ("1.5 GiB", 1610612736),
        ("12 KiB", 12288),
        ("3 B", 3),
        ("2 TB", 2 * 1000**4),
        ("1..5 GiB", None),
        ("lots", None),
        ("", None),
    ],
)
def test_parse_size(text: str, expected) -> None:
    assert parse_size(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Thu, 01 Oct 2026 12:00:00 +0000", T0),
        ("Thu, 01 Oct 2026 14:00:00 +0200", T0),
        ("Thu, 01 Oct 2026 12:00:00 GMT", T0),
        ("2026-10-01T12:00:00Z", T0),
        (
            "2026-10-01T14:00:00+02:00",
            datetime(2026, 10, 1, 14, tzinfo=timezone(timedelta(hours=2))),
        ),
        ("2026-10-01T12:00:00", T0),
        ("yesterday", None),
        ("0001-01-01T00:00:00+01:00", None),
        ("0999-01-01T00:00:00Z", datetime(999, 1, 1, tzinfo=UTC)),
    ],
    ids=[
        "utc",
        "offset",
        "gmt",
        "iso-z",
        "iso-offset",
        "iso-naive",
        "words",
        "out-of-range",
        "old",
    ],
)
def test_parse_date(text: str, expected) -> None:
    parsed = parse_date(text)
    assert parsed == expected
    if parsed is not None:
        assert parsed.tzinfo is not None
        assert parsed.astimezone(UTC) == expected.astimezone(UTC)
