"""Feeds end to end: Charon subscribes to the fake's RSS feeds over real HTTP."""

import uuid

import pytest

from tests.e2e.conftest import Stack
from tests.e2e.test_flow import TERMINAL, create_rule, unique_token, wait_for

pytestmark = pytest.mark.e2e


@pytest.fixture
def feed(stack: Stack):
    body = {"name": f"e2e-{uuid.uuid4().hex[:8]}", "url": f"{stack.fake_service}/feeds/tv.xml"}
    response = stack.charon.post("/feeds", json=body)
    assert response.status_code == 201, response.text
    created = response.json()
    yield created
    stack.fake.post("/_control/feeds/tv/heal")
    stack.charon.delete(f"/feeds/{created['id']}")


def items_of(stack: Stack, feed: dict, **params) -> list[dict]:
    query = {"feed_id": feed["id"], "limit": 200, **params}
    return stack.charon.get("/feeds/items", params=query).json()["items"]


def test_subscribing_reads_the_feed_right_away(stack: Stack, feed: dict) -> None:
    assert feed["last_error"] is None
    assert feed["title"] == "Fake Tracker · TV"
    items = items_of(stack, feed)
    names = [i["name"] for i in items]
    assert "The.Expanse.S02E06.1080p.WEB-DL.x264.mkv" in names
    assert not any(n.endswith(".torrent") for n in names)
    assert any(i["published_estimated"] for i in items)


def test_a_published_item_matches_a_rule_and_downloads_into_place(stack: Stack, feed: dict) -> None:
    token = unique_token()
    create_rule(stack, token)
    name = f"Fresh.{token}.XYZ.mkv"
    published = stack.fake.post("/_control/feeds/tv/publish", json={"name": name}).json()
    stack.charon.post(f"/feeds/{feed['id']}/refresh")

    [item] = items_of(stack, feed, q=token)
    assert item["match"]["new_name"] == f"Fresh.{token}.ABC.mkv"
    assert item["seen"] is False

    response = stack.charon.post(f"/feeds/items/{published['info_hash']}/download", json={})
    assert response.status_code == 202, response.text
    done = wait_for(stack, response.json()["id"], TERMINAL)
    assert done["status"] == "done"
    assert (stack.library_local / token / f"Fresh.{token}.ABC.mkv").exists()
    again = stack.charon.post(f"/feeds/items/{published['info_hash']}/download", json={})
    assert again.status_code == 200


def test_a_broken_feed_reports_why_until_it_heals(stack: Stack, feed: dict) -> None:
    stack.fake.post("/_control/feeds/tv/break", json={"mode": "http_error"})
    broken = stack.charon.post(f"/feeds/{feed['id']}/refresh").json()
    assert broken["last_error"]["code"] == "feed_http_error"
    stack.fake.post("/_control/feeds/tv/heal")
    healed = stack.charon.post(f"/feeds/{feed['id']}/refresh").json()
    assert healed["last_error"] is None
