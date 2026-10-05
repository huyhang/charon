import itertools
import json
from collections import Counter

import httpx
import pytest

from fake_ds import seed
from fake_ds.seed import COLLIDING_FILE, LIBRARY_FOLDERS, SAMPLE_KEYS, SAMPLES, Seeder, SeedReport

ADMIN = {"name": "admin", "role": "admin", "auth_enabled": True}


class FakeServices:
    """Just enough of Charon's API and the fake's control API for the seeder."""

    def __init__(self, roots=("/library",), principal=ADMIN, keys=(), rules=()) -> None:
        self.roots = list(roots)
        self.principal = principal
        self.keys = [dict(key) for key in keys]
        self.rules = [dict(rule) for rule in rules]
        self.tasks: list[dict] = []
        self.control: list[tuple[str, str]] = []
        self.cancelled: list[str] = []
        self.revoked: list[str] = []
        self._ids = itertools.count(1)

    def charon(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path.removeprefix("/api/v1")
        body = json.loads(request.content) if request.content else None
        if (method, path) == ("GET", "/destinations/roots"):
            return httpx.Response(200, json={"roots": self.roots})
        if (method, path) == ("GET", "/rules"):
            return httpx.Response(200, json=self.rules)
        if (method, path) == ("POST", "/rules"):
            self.rules.append(body)
            return httpx.Response(201, json=body)
        if (method, path) == ("POST", "/downloads"):
            job_id = f"job-{next(self._ids)}"
            self.tasks.append(
                {"id": f"task-{job_id}", "additional": {"detail": {"uri": body["magnet"]}}}
            )
            return httpx.Response(202, json={"id": job_id})
        if method == "DELETE" and path.startswith("/downloads/"):
            self.cancelled.append(path.rsplit("/", 1)[1])
            return httpx.Response(200, json={})
        if (method, path) == ("GET", "/auth/me"):
            return httpx.Response(200, json=self.principal)
        if (method, path) == ("GET", "/api-keys"):
            return httpx.Response(200, json=self.keys)
        if (method, path) == ("POST", "/api-keys"):
            key = {"id": f"key-{next(self._ids)}", **body}
            self.keys.append(key)
            return httpx.Response(201, json=key)
        if method == "DELETE" and path.startswith("/api-keys/"):
            self.revoked.append(path.rsplit("/", 1)[1])
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"error": {"code": "not_found", "message": path}})

    def fake(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/_control/tasks":
            return httpx.Response(200, json=self.tasks)
        _, _, _, task_id, action = request.url.path.split("/")
        self.control.append((task_id, action))
        return httpx.Response(204)

    def seeder(self, library=None) -> Seeder:
        charon = httpx.Client(
            base_url="http://charon/api/v1", transport=httpx.MockTransport(self.charon)
        )
        fake = httpx.Client(base_url="http://fake", transport=httpx.MockTransport(self.fake))
        return Seeder(charon, fake, library, new_hash=lambda: "0" * 40)


def test_every_sample_is_steered_to_its_outcome() -> None:
    services = FakeServices()
    report = services.seeder().run()
    outcomes = Counter(sample.outcome for sample in SAMPLES)
    actions = Counter(action for _, action in services.control)
    assert len(report.jobs) == len(SAMPLES)
    assert actions == {
        "complete": outcomes["done"] + outcomes["collides"],
        "fail": outcomes["failed"],
    }
    assert len(services.cancelled) == outcomes["cancelled"]


def test_rules_file_into_the_first_root_and_are_added_once() -> None:
    services = FakeServices(roots=["/media", "/other"], rules=[{"name": "Anime"}])
    report = services.seeder().run()
    assert "Anime" not in report.rules_created
    assert {rule["destination"].rsplit("/", 1)[0] for rule in services.rules[1:]} == {"/media"}
    assert [rule["name"] for rule in services.rules].count("Anime") == 1


def test_no_rule_roots_stops_before_changing_anything() -> None:
    services = FakeServices(roots=[])
    with pytest.raises(SystemExit, match="CHARON_RULE_ROOTS"):
        services.seeder().run()
    assert (services.rules, services.tasks, services.keys) == ([], [], [])


@pytest.mark.parametrize(
    ("principal", "existing", "issued"),
    [
        (ADMIN, [], [name for name, _ in SAMPLE_KEYS]),
        (ADMIN, [{"id": "k0", "name": "laptop"}], []),
        ({**ADMIN, "role": "client"}, [], []),
        ({**ADMIN, "auth_enabled": False}, [], []),
    ],
    ids=["admin-first-run", "keys-already-there", "client-key", "auth-disabled"],
)
def test_keys_are_issued_only_by_an_admin_with_none_yet(principal, existing, issued) -> None:
    services = FakeServices(principal=principal, keys=existing)
    report = services.seeder().run()
    assert report.keys_issued == issued
    assert len(services.revoked) == (1 if issued else 0)


@pytest.mark.parametrize("with_library", [True, False])
def test_library_folders_and_the_colliding_file(tmp_path, with_library: bool) -> None:
    library = tmp_path / "library"
    FakeServices().seeder(library if with_library else None).run()
    assert all((library / folder).is_dir() for folder in LIBRARY_FOLDERS) is with_library
    assert (library / COLLIDING_FILE).exists() is with_library


@pytest.mark.parametrize(
    ("argv", "charon_url", "headers", "library"),
    [
        ([], "http://127.0.0.1:8080/api/v1", {"x-api-key": "dev-key"}, None),
        (
            ["--charon", "http://nas:8080", "--api-key", "", "--library", "var/lib"],
            "http://nas:8080/api/v1",
            {},
            "var/lib",
        ),
    ],
    ids=["defaults", "overrides"],
)
def test_main_wires_arguments_and_prints_a_report(
    monkeypatch, capsys, argv, charon_url, headers, library
) -> None:
    seen = {}

    class StubSeeder:
        def __init__(self, charon: httpx.Client, fake: httpx.Client, lib) -> None:
            seen.update(charon=str(charon.base_url), key=charon.headers.get("x-api-key"), lib=lib)

        def run(self) -> SeedReport:
            return SeedReport(rules_created=["TV"], jobs={"a": "1", "b": "2"}, keys_issued=[])

    monkeypatch.setattr(seed, "Seeder", StubSeeder)
    seed.main(argv)
    assert seen["charon"].rstrip("/") == charon_url
    assert seen["key"] == headers.get("x-api-key")
    assert (str(seen["lib"]) if seen["lib"] else None) == library
    out = capsys.readouterr().out
    assert "rules created: TV" in out
    assert "downloads submitted: 2" in out
    assert "keys issued: none (already there)" in out


def test_main_explains_an_unreachable_stack(monkeypatch) -> None:
    class Unreachable:
        def __init__(self, *_: object) -> None: ...

        def run(self) -> SeedReport:
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(seed, "Seeder", Unreachable)
    with pytest.raises(SystemExit, match="Is `make ui-dev` running"):
        seed.main(["--charon", "http://127.0.0.1:1"])
