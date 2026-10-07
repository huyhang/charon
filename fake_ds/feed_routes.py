"""Serves the fake feeds, plus test-only endpoints for steering them."""

import hashlib
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from fake_ds.feeds import FakeFeed, FakeFeeds, FeedMode, render

router = APIRouter(tags=["feeds"])


class PublishRequest(BaseModel):
    name: str | None = None


class BreakRequest(BaseModel):
    mode: FeedMode = FeedMode.HTTP_ERROR


def _feeds(request: Request) -> FakeFeeds:
    return request.app.state.feeds


def _require(feed: FakeFeed | None) -> FakeFeed:
    if feed is None:
        raise HTTPException(404, "feed not found")
    return feed


@router.get("/feeds/{slug}.xml")
def serve_feed(slug: str, request: Request) -> Response:
    """The feed as RSS, honouring If-None-Match like a real server."""
    feed = _require(_feeds(request).get(slug))
    if feed.mode is FeedMode.HTTP_ERROR:
        return Response("tracker is down", status_code=503)
    if feed.mode is FeedMode.BAD_XML:
        return Response("<html><body>Please log in</body></html>", media_type="text/html")
    body = render(feed)
    etag = f'"{hashlib.sha1(body).hexdigest()}"'
    if request.headers.get("If-None-Match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(body, media_type="application/rss+xml", headers={"ETag": etag})


@router.get("/_control/feeds")
def list_feeds(request: Request) -> list[dict[str, Any]]:
    return [FakeFeeds.snapshot(feed) for feed in _feeds(request).all()]


@router.post("/_control/feeds/{slug}/publish")
def publish(slug: str, request: Request, body: PublishRequest | None = None) -> dict[str, Any]:
    feeds = _feeds(request)
    _require(feeds.get(slug))
    item = feeds.publish(slug, (body or PublishRequest()).name)
    assert item is not None
    return {"name": item.name, "info_hash": item.info_hash, "magnet": item.magnet}


@router.post("/_control/feeds/{slug}/break")
def break_feed(slug: str, request: Request, body: BreakRequest | None = None) -> dict[str, Any]:
    mode = (body or BreakRequest()).mode
    return FakeFeeds.snapshot(_require(_feeds(request).set_mode(slug, mode)))


@router.post("/_control/feeds/{slug}/heal")
def heal_feed(slug: str, request: Request) -> dict[str, Any]:
    return FakeFeeds.snapshot(_require(_feeds(request).set_mode(slug, FeedMode.OK)))
