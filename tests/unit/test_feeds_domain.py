from datetime import timedelta

import pytest

from charon.domain.feeds import (
    PUBLISHED_GRACE,
    FeedSpec,
    FeedUpdate,
    check_feed_url,
    feed_host,
    feed_url_key,
    is_auto_download_candidate,
    mask_url,
)
from tests.unit.fakes import T0
from tests.unit.feed_samples import make_feed, make_item

LATER = T0 + timedelta(hours=1)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://nyaa.example/?page=rss&magnets", "https://nyaa.example/?page=••••&magnets="),
        ("https://t.example/rss?passkey=abc123", "https://t.example/rss?passkey=••••"),
        (
            "https://t.example/rss/0123456789abcdef0123/feed.xml",
            "https://t.example/rss/••••/feed.xml",
        ),
        (
            "https://t.example/rss/latest-episodes-1080p",
            "https://t.example/rss/latest-episodes-1080p",
        ),
        ("https://user:pw@t.example:8443/rss", "https://••••@t.example:8443/rss"),
        ("http://192.168.1.5:9117/api?apikey=k", "http://192.168.1.5:9117/api?apikey=••••"),
        ("https://t.example/rss#frag", "https://t.example/rss"),
        (
            "https://t.example/u/123e4567-e89b-12d3-a456-426614174000/rss",
            "https://t.example/u/••••/rss",
        ),
        ("https://t.example/rss/PASSKEY012", "https://t.example/rss/••••"),
        ("https://t.example/rss;sid=abc123/feed", "https://t.example/rss;sid=••••/feed"),
        ("http://t.example:99999/rss", "http://t.example:99999/rss"),
    ],
    ids=[
        "query",
        "passkey",
        "token-path",
        "plain-path",
        "userinfo",
        "lan",
        "fragment",
        "uuid",
        "short-token",
        "path-params",
        "bad-port-never-raises",
    ],
)
def test_mask_url_hides_what_looks_secret(url: str, expected: str) -> None:
    assert mask_url(url) == expected


@pytest.mark.parametrize(
    ("url", "valid"),
    [
        ("https://t.example/rss", True),
        ("  http://t.example/rss  ", True),
        ("ftp://t.example/rss", False),
        ("https:///rss", False),
        ("t.example/rss", False),
        ("magnet:?xt=urn:btih:abc", False),
        ("http://prowlarr:9696/api/v1/feed", True),
        ("http://t.example:99999/rss", False),
        ("http://t.example:abc/rss", False),
        ("http://t.example:0/rss", False),
        ("http://a..b/rss", False),
        ("http://xn--zz.example/rss", False),
        (f"http://{'x' * 64}.example/rss", False),
    ],
)
def test_check_feed_url(url: str, valid: bool) -> None:
    if valid:
        assert check_feed_url(url) == url.strip()
    else:
        with pytest.raises(ValueError):
            check_feed_url(url)


def test_specs_validate_urls() -> None:
    with pytest.raises(ValueError):
        FeedSpec(name="x", url="ftp://x")
    assert FeedUpdate(name="x").url is None
    with pytest.raises(ValueError):
        FeedUpdate(name="x", url="nope")


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("https://T.example:443/rss?k=1#top", "https://t.example/rss?k=1", True),
        ("http://t.example:80/rss", "HTTP://t.example/rss", True),
        ("https://t.example", "https://t.example/", True),
        ("https://t.example/rss?k=1", "https://t.example/rss?k=2", False),
        ("https://t.example/RSS", "https://t.example/rss", False),
        ("https://a@t.example/rss", "https://b@t.example/rss", False),
    ],
    ids=["case-port-fragment", "http-default-port", "empty-path", "query", "path-case", "user"],
)
def test_feed_url_key_tells_the_same_feed(a: str, b: str, same: bool) -> None:
    assert (feed_url_key(a) == feed_url_key(b)) is same


def test_feed_host_names_only_the_host() -> None:
    assert feed_host("https://u:p@t.example:8443/rss?passkey=x") == "t.example"


@pytest.mark.parametrize(
    ("overrides", "now", "due"),
    [
        ({}, T0, True),
        ({"enabled": False}, T0, False),
        ({"last_checked_at": T0}, T0 + timedelta(minutes=14), False),
        ({"last_checked_at": T0}, T0 + timedelta(minutes=15), True),
        ({"last_checked_at": T0, "refresh_minutes": 60}, T0 + timedelta(minutes=30), False),
    ],
    ids=["never-checked", "disabled", "too-soon", "interval-passed", "custom-interval"],
)
def test_feed_is_due(overrides: dict, now, due: bool) -> None:
    assert make_feed(**overrides).is_due(now) is due


@pytest.mark.parametrize(
    ("existing", "incoming", "expected"),
    [
        ({"published_at": LATER}, {"published_at": T0}, T0),
        ({"published_at": T0}, {"published_at": LATER}, None),
        (
            {"published_at": LATER, "published_estimated": True},
            {"published_at": LATER + timedelta(hours=1)},
            LATER + timedelta(hours=1),
        ),
        ({"published_at": LATER}, {"published_at": T0, "published_estimated": True}, None),
    ],
    ids=["earlier-wins", "later-ignored", "real-beats-estimate", "estimate-ignored"],
)
def test_date_changes_keep_the_earliest_real_date(existing, incoming, expected) -> None:
    changes = make_item(**existing).date_changes(make_item(**incoming))
    if expected is None:
        assert changes is None
    else:
        assert changes == {"published_at": expected, "published_estimated": False}


SINCE = T0 + timedelta(minutes=10)


@pytest.mark.parametrize(
    ("feed", "item", "expected"),
    [
        (
            {"auto_download": True, "auto_download_since": SINCE},
            {"first_seen_at": LATER, "published_at": LATER},
            True,
        ),
        (
            {"auto_download": False, "auto_download_since": SINCE},
            {"first_seen_at": LATER, "published_at": LATER},
            False,
        ),
        ({"auto_download": True}, {"first_seen_at": LATER, "published_at": LATER}, False),
        (
            {"auto_download": True, "auto_download_since": SINCE, "enabled": False},
            {"first_seen_at": LATER, "published_at": LATER},
            False,
        ),
        (
            {"auto_download": True, "auto_download_since": SINCE},
            {"first_seen_at": LATER, "published_at": SINCE - PUBLISHED_GRACE},
            True,
        ),
        (
            {"auto_download": True, "auto_download_since": SINCE},
            {
                "first_seen_at": LATER,
                "published_at": SINCE - PUBLISHED_GRACE - timedelta(minutes=1),
            },
            False,
        ),
        (
            {"auto_download": True, "auto_download_since": SINCE},
            {"first_seen_at": LATER, "published_at": T0, "published_estimated": True},
            True,
        ),
        (
            {"auto_download": True, "auto_download_since": SINCE},
            {"first_seen_at": LATER, "published_at": LATER, "job_id": "job-1"},
            False,
        ),
    ],
    ids=["new", "off", "no-since", "paused", "dated-within-grace", "old-date", "undated", "taken"],
)
def test_is_auto_download_candidate(feed: dict, item: dict, expected: bool) -> None:
    assert is_auto_download_candidate(make_feed(**feed), make_item(**item)) is expected
