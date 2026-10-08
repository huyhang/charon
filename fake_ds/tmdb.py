"""A fake TMDB, for trying Charon's title lookup without a TMDB account.

Like TMDB's v3 API, it wants a bearer token, answers multi search with movies, shows and
people in TMDB's shapes (movies have `title`, shows `name`), and answers 429 when sent more
than its limit. It also records the busiest 10 seconds it has seen, so tests can check that
Charon never sends more than its budget. Control endpoints make it throttle or fail.
"""

import re
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

DEV_TOKEN = "dev-tmdb-token"
PAGE_SIZE = 20


class TmdbMode(StrEnum):
    OK = "ok"
    # Answers every search with 429, as TMDB does when a client sends too much.
    THROTTLED = "throttled"
    # Answers every search with 503.
    DOWN = "down"


@dataclass(frozen=True)
class Entry:
    result: dict[str, Any]
    # Other names it is found by, as TMDB finds shows by their alternative titles.
    aliases: tuple[str, ...] = ()


def _tv(id_: int, name: str, original: str, aired: str, overview: str, *aliases: str) -> Entry:
    result = {
        "id": id_,
        "media_type": "tv",
        "name": name,
        "original_name": original,
        "first_air_date": aired,
        "overview": overview,
        "origin_country": ["JP"] if original != name else ["US"],
        "poster_path": None,
    }
    return Entry(result, aliases)


def _movie(id_: int, title: str, original: str, released: str, overview: str) -> Entry:
    result = {
        "id": id_,
        "media_type": "movie",
        "title": title,
        "original_title": original,
        "release_date": released,
        "overview": overview,
        "video": False,
        "poster_path": None,
    }
    return Entry(result)


def _person(id_: int, name: str, *aliases: str) -> Entry:
    result = {
        "id": id_,
        "media_type": "person",
        "name": name,
        "original_name": name,
        "known_for_department": "Writing",
        "profile_path": None,
        "known_for": [],
    }
    return Entry(result, aliases)


# Sample data in TMDB's shapes, covering the fake feeds' releases.
CATALOGUE = [
    _tv(
        220542,
        "The Apothecary Diaries",
        "薬屋のひとりごと",
        "2023-10-22",
        "Maomao, a young apothecary, is sold into service at the imperial palace.",
        "Kusuriya no Hitorigoto",
    ),
    # A person, as multi search finds them too; Charon leaves them out.
    _person(3300101, "Natsu Hyuuga", "Kusuriya no Hitorigoto"),
    _tv(
        209867,
        "Frieren: Beyond Journey's End",
        "葬送のフリーレン",
        "2023-09-29",
        "An elf mage outlives the hero party she once travelled with.",
        "Sousou no Frieren",
    ),
    _tv(
        240411,
        "DAN DA DAN",
        "ダンダダン",
        "2024-10-04",
        "A girl who believes in ghosts meets a boy who believes in aliens.",
        "Dandadan",
    ),
    _movie(693134, "Dune: Part Two", "Dune: Part Two", "2024-02-27", "Paul joins the Fremen."),
    _movie(438631, "Dune", "Dune", "2021-09-15", "Paul Atreides travels to Arrakis."),
    _tv(63639, "The Expanse", "The Expanse", "2015-12-14", "Humanity has colonised the system."),
    _tv(95396, "Severance", "Severance", "2022-02-17", "Office workers split their memories."),
    _tv(83867, "Andor", "Andor", "2022-09-21", "Cassian Andor's path to rebellion."),
    _tv(126308, "Shōgun", "Shōgun", "2024-02-27", "Feudal Japan, 1600.", "Shogun"),
    _movie(
        900667,
        "One Piece Film Red",
        "ONE PIECE FILM RED",
        "2022-08-06",
        "Uta, the world's most beloved singer, reveals herself.",
    ),
]

_NOT_WORD = re.compile(r"[\W_]+")


def _words(text: str) -> str:
    return _NOT_WORD.sub(" ", text.casefold()).strip()


def _names(entry: Entry) -> list[str]:
    result = entry.result
    keys = ("title", "original_title", "name", "original_name")
    return [str(result[key]) for key in keys if key in result] + list(entry.aliases)


def unauthorized_body() -> dict[str, Any]:
    return {
        "status_code": 7,
        "status_message": "Invalid API key: You must be granted a valid key.",
        "success": False,
    }


def throttled_body(limit: int) -> dict[str, Any]:
    return {
        "status_code": 25,
        "status_message": f"Your request count is over the allowed limit of ({limit}).",
        "success": False,
    }


class FakeTmdb:
    def __init__(
        self,
        token: str = DEV_TOKEN,
        limit: int = 40,
        window_seconds: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        catalogue: list[Entry] | None = None,
    ) -> None:
        self.token = token
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._catalogue = CATALOGUE if catalogue is None else catalogue
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.mode = TmdbMode.OK
            self.requests = 0
            self.busiest_window = 0
            self._recent: deque[float] = deque()

    def authorized(self, header: str | None) -> bool:
        return header == f"Bearer {self.token}"

    def record(self) -> bool:
        """Count a request arriving now; False if it is over the limit for the window."""
        with self._lock:
            now = self._clock()
            self._recent.append(now)
            while self._recent[0] <= now - self.window:
                self._recent.popleft()
            self.requests += 1
            self.busiest_window = max(self.busiest_window, len(self._recent))
            return len(self._recent) <= self.limit

    def search(self, query: str) -> list[dict[str, Any]]:
        wanted = _words(query)
        if not wanted:
            return []
        return [
            entry.result
            for entry in self._catalogue
            if any(wanted in _words(name) for name in _names(entry))
        ]

    def page(self, query: str, page: int) -> dict[str, Any]:
        """A multi search answer, as TMDB pages it."""
        found = self.search(query)
        start = (page - 1) * PAGE_SIZE
        return {
            "page": page,
            "results": found[start : start + PAGE_SIZE],
            "total_pages": max(1, -(-len(found) // PAGE_SIZE)),
            "total_results": len(found),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "requests": self.requests,
            "busiest_window": self.busiest_window,
            "limit": self.limit,
            "window_seconds": self.window,
        }
