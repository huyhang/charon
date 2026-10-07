"""Fill a running Charon + fake Download Station with realistic sample data, for UI work.

python -m fake_ds.seed --charon http://127.0.0.1:8080 --fake-ds http://127.0.0.1:5000 \
    --api-key dev-key --library var/library

Creates a few rules, downloads that end up in every state (done, downloading, failed,
cancelled, and a failed move), some API keys, and subscriptions to the fake's feeds with
items in every state (new, seen, already in Charon, downloaded). Safe to re-run: rules,
keys and feeds are only added once, and downloads get fresh hashes each time.
"""

import argparse
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import httpx

Outcome = Literal["done", "downloading", "failed", "cancelled", "collides"]

QUALITY_TAGS = r"\.(?:2160p|1080p|720p|WEB-DL|WEBRip|BluRay|x264|x265|HEVC)(?=\.)"


def sample_rules(root: str) -> list[dict]:
    return [
        {
            "name": "TV episodes",
            "priority": 10,
            "match_type": "glob",
            "pattern": "*S[0-9][0-9]E[0-9][0-9]*",
            "steps": [{"op": "regex_replace", "find": QUALITY_TAGS, "replace": ""}],
            "destination": f"{root}/tv",
        },
        {
            "name": "Anime",
            "priority": 20,
            "match_type": "glob",
            "pattern": "[[]*",
            "steps": [
                {"op": "regex_replace", "find": r"^\[[^\]]+\]\s*", "replace": ""},
                {"op": "regex_replace", "find": r" \((?:1080p|720p)\)", "replace": ""},
            ],
            "destination": f"{root}/anime",
        },
        {
            "name": "Movies",
            "priority": 30,
            "match_type": "regex",
            "pattern": r"\.(?:19|20)\d{2}\.",
            "steps": [
                {"op": "regex_replace", "find": QUALITY_TAGS, "replace": ""},
                {"op": "regex_replace", "find": r"\.((?:19|20)\d{2})(?=\.)", "replace": r" (\1)"},
                {"op": "regex_replace", "find": r"\.(?=[^.]*\.)", "replace": " "},
            ],
            "destination": f"{root}/movies",
        },
        {
            "name": "Linux ISOs",
            "priority": 40,
            "enabled": False,
            "match_type": "glob",
            "pattern": "*.iso",
            "destination": f"{root}/isos",
        },
    ]


@dataclass(frozen=True)
class Sample:
    name: str
    outcome: Outcome


SAMPLES = [
    Sample("The.Expanse.S02E05.1080p.WEB-DL.x264.mkv", "done"),
    Sample("Dune.Part.Two.2024.2160p.BluRay.x265.mkv", "done"),
    Sample("[SubsPlease] Frieren - 12 (1080p).mkv", "done"),
    Sample("ubuntu-24.04.1-desktop-amd64.iso", "done"),
    Sample("Andor.S01E01.1080p.WEB-DL.mkv", "collides"),
    Sample("Big.Buck.Bunny.2008.1080p.mkv", "failed"),
    Sample("Some.Old.Show.S01E01.720p.mkv", "cancelled"),
    Sample("Severance.S02E03.1080p.WEB-DL.mkv", "downloading"),
    Sample("Shogun.2024.S01E04.2160p.mkv", "downloading"),
]

# Already at the destination, so "Andor" fails with destination_exists.
COLLIDING_FILE = "tv/Andor.S01E01.mkv"
LIBRARY_FOLDERS = ["tv", "anime", "movies", "isos"]
SAMPLE_KEYS = [("phone", "client"), ("sonarr", "client"), ("old-laptop", "client")]
REVOKED_KEY = "old-laptop"
# (Charon feed name, fake feed slug). Charon fetches them from the fake.
SAMPLE_FEEDS = [("Fake TV", "tv"), ("Fake Anime", "anime")]
# Pasted as a magnet before subscribing, so the inbox shows it as already in Charon.
ALREADY_ADDED = "Andor.S01E02.1080p.WEB-DL.mkv"
# Downloaded from the inbox and finished, so the inbox shows it as done.
DOWNLOADED_FROM_FEED = "Severance.S02E04.1080p.WEB-DL.mkv"


# How often to try cancelling a job that keeps changing under the cancel (job_changed).
CANCEL_ATTEMPTS = 5


def _is_error(response: httpx.Response, code: str) -> bool:
    if response.status_code != 409:
        return False
    return response.json().get("error", {}).get("code") == code


@dataclass
class SeedReport:
    rules_created: list[str] = field(default_factory=list)
    # Sample name -> Charon job id.
    jobs: dict[str, str] = field(default_factory=dict)
    keys_issued: list[str] = field(default_factory=list)
    feeds_subscribed: list[str] = field(default_factory=list)


def magnet_for(name: str, info_hash: str) -> str:
    return f"magnet:?xt=urn:btih:{info_hash}&dn={quote(name)}"


class Seeder:
    """Talks only HTTP to Charon and the fake, plus the local library folder if given."""

    def __init__(
        self,
        charon: httpx.Client,
        fake: httpx.Client,
        library: Path | None,
        feed_base: str | None = None,
        new_hash: Callable[[], str] = lambda: secrets.token_hex(20),
    ) -> None:
        self._charon = charon
        self._fake = fake
        self._library = library
        # Where Charon reaches the fake's feeds; None skips feeds.
        self._feed_base = feed_base
        self._new_hash = new_hash

    def run(self) -> SeedReport:
        report = SeedReport()
        root = self._root()
        self._prepare_library()
        report.rules_created = self._seed_rules(root)
        report.jobs = {sample.name: self._seed_download(sample) for sample in SAMPLES}
        report.keys_issued = self._seed_keys()
        report.feeds_subscribed = self._seed_feeds()
        return report

    def _root(self) -> str:
        roots = self._ok(self._charon.get("/destinations/roots"))["roots"]
        if not roots:
            raise SystemExit("Charon has no CHARON_RULE_ROOTS, so there is nowhere to file into")
        return roots[0]

    def _prepare_library(self) -> None:
        if self._library is None:
            return
        for folder in LIBRARY_FOLDERS:
            (self._library / folder).mkdir(parents=True, exist_ok=True)
        (self._library / COLLIDING_FILE).touch()

    def _seed_rules(self, root: str) -> list[str]:
        existing = {rule["name"] for rule in self._ok(self._charon.get("/rules"))}
        created = []
        for rule in sample_rules(root):
            if rule["name"] not in existing:
                self._ok(self._charon.post("/rules", json=rule))
                created.append(rule["name"])
        return created

    def _seed_download(self, sample: Sample) -> str:
        magnet = magnet_for(sample.name, self._new_hash())
        job = self._ok(self._charon.post("/downloads", json={"magnet": magnet}))
        if sample.outcome == "cancelled":
            # Right away: the fake finishes downloads on its own, after which they can't be.
            self._cancel(job["id"])
        elif sample.outcome in ("done", "collides"):
            self._ok(self._fake.post(f"/_control/tasks/{self._task_id(magnet)}/complete"))
        elif sample.outcome == "failed":
            failure = {"detail": "broken_link"}
            self._ok(self._fake.post(f"/_control/tasks/{self._task_id(magnet)}/fail", json=failure))
        return job["id"]

    def _cancel(self, job_id: str) -> None:
        """Cancel a job, again if Charon's watcher updated it at that very moment."""
        for _ in range(CANCEL_ATTEMPTS):
            response = self._charon.delete(f"/downloads/{job_id}")
            if not _is_error(response, "job_changed"):
                break
        self._ok(response)

    def _task_id(self, magnet: str) -> str:
        tasks = self._ok(self._fake.get("/_control/tasks"))
        return next(t["id"] for t in tasks if t["additional"]["detail"]["uri"] == magnet)

    def _seed_keys(self) -> list[str]:
        me = self._ok(self._charon.get("/auth/me"))
        if not me["auth_enabled"] or me["role"] != "admin":
            return []
        if self._ok(self._charon.get("/api-keys")):
            return []
        issued = {}
        for name, role in SAMPLE_KEYS:
            body = {"name": name, "role": role}
            issued[name] = self._ok(self._charon.post("/api-keys", json=body))
        self._ok(self._charon.delete(f"/api-keys/{issued[REVOKED_KEY]['id']}"))
        return list(issued)

    def _seed_feeds(self) -> list[str]:
        if self._feed_base is None:
            return []
        existing = {feed["name"] for feed in self._ok(self._charon.get("/feeds"))}
        missing = [(name, slug) for name, slug in SAMPLE_FEEDS if name not in existing]
        if not missing:
            return []
        samples = self._fake_feed_items()
        self._ok(self._charon.post("/downloads", json={"magnet": samples[ALREADY_ADDED]["magnet"]}))
        feeds = [self._subscribe(name, slug) for name, slug in missing]
        self._download_from_feed(samples[DOWNLOADED_FROM_FEED])
        self._mark_everything_seen()
        self._publish_fresh_items(feeds)
        return [name for name, _ in missing]

    def _fake_feed_items(self) -> dict[str, dict[str, Any]]:
        feeds = self._ok(self._fake.get("/_control/feeds"))
        return {item["name"]: item for feed in feeds for item in feed["items"]}

    def _subscribe(self, name: str, slug: str) -> dict[str, Any]:
        body = {"name": name, "url": f"{self._feed_base}/feeds/{slug}.xml", "refresh_minutes": 5}
        return {**self._ok(self._charon.post("/feeds", json=body)), "slug": slug}

    def _download_from_feed(self, item: dict[str, Any]) -> None:
        response = self._charon.post(f"/feeds/items/{item['info_hash']}/download", json={})
        self._ok(response)
        # 200 means it was already in Charon (e.g. seeded before), with no new task to finish.
        if response.status_code == 202:
            task_id = self._task_id(item["magnet"])
            self._ok(self._fake.post(f"/_control/tasks/{task_id}/complete"))

    def _mark_everything_seen(self) -> None:
        items = self._ok(self._charon.get("/feeds/items", params={"limit": 200}))["items"]
        if items:
            newest = max(item["first_seen_at"] for item in items)
            self._ok(self._charon.post("/feeds/items/seen-all", json={"up_to": newest}))

    def _publish_fresh_items(self, feeds: list[dict[str, Any]]) -> None:
        """New items after everything was marked seen, so the inbox shows what's new."""
        for feed in feeds:
            self._ok(self._fake.post(f"/_control/feeds/{feed['slug']}/publish"))
            self._ok(self._charon.post(f"/feeds/{feed['id']}/refresh"))

    @staticmethod
    def _ok(response: httpx.Response):
        response.raise_for_status()
        return response.json() if response.content else None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--charon", default="http://127.0.0.1:8080")
    parser.add_argument("--fake-ds", default="http://127.0.0.1:5000")
    parser.add_argument("--api-key", default="dev-key")
    parser.add_argument("--library", type=Path, help="Local path of the first rule root")
    parser.add_argument(
        "--feed-base", help="The fake's address as Charon reaches it (default: --fake-ds)"
    )
    args = parser.parse_args(argv)
    headers = {"X-API-Key": args.api_key} if args.api_key else {}
    try:
        with (
            httpx.Client(base_url=f"{args.charon}/api/v1", headers=headers, timeout=15) as charon,
            httpx.Client(base_url=args.fake_ds, timeout=15) as fake,
        ):
            feed_base = args.feed_base or args.fake_ds
            report = Seeder(charon, fake, args.library, feed_base=feed_base).run()
    except httpx.HTTPError as exc:
        raise SystemExit(
            f"Couldn't seed Charon at {args.charon} / fake at {args.fake_ds}: {exc}\n"
            "Is `make ui-dev` running? Give `make ui-seed` the same CHARON_PORT / FAKE_DS_PORT."
        ) from exc
    print(f"rules created: {', '.join(report.rules_created) or 'none (already there)'}")
    print(f"downloads submitted: {len(report.jobs)}")
    print(f"keys issued: {', '.join(report.keys_issued) or 'none (already there)'}")
    print(f"feeds subscribed: {', '.join(report.feeds_subscribed) or 'none (already there)'}")


if __name__ == "__main__":
    main()
