from pathlib import PurePosixPath as P

import pytest

from charon.domain.destinations import DestinationPolicy
from charon.errors import InvalidInputError, NotFoundError
from charon.services.destination_service import DestinationService, Folder
from tests.unit.fakes import FakeFileOps

POLICY = DestinationPolicy.of(["/media", "/library"], ["/media/data"])


def make_service(
    folders: dict[str, list[str]] | None = None,
    symlinks: dict[str, str] | None = None,
    roots: tuple[str, ...] = ("/media", "/library"),
) -> tuple[DestinationService, FakeFileOps]:
    files = FakeFileOps()
    files.folders = {P(path): names for path, names in (folders or {}).items()}
    files.symlinks = {P(link): P(target) for link, target in (symlinks or {}).items()}
    return DestinationService(roots, POLICY, files), files


@pytest.mark.parametrize(
    ("roots", "expected"),
    [
        (("/media", "/library"), ["/media", "/library"]),
        (("/media/", "/media", "/library/./"), ["/media", "/library"]),
        (("/media/data", "/library"), ["/library"]),
        ((), []),
    ],
)
def test_roots_are_normalized_deduplicated_and_allowed(
    roots: tuple[str, ...], expected: list[str]
) -> None:
    service, _ = make_service(roots=roots)
    assert service.roots() == expected


@pytest.mark.parametrize(
    ("folders", "symlinks", "expected"),
    [
        ({"/media": ["tv", "movies"]}, {}, ["movies", "tv"]),
        ({"/media": [".hidden", "tv"]}, {}, ["tv"]),
        ({"/media": ["data", "tv"]}, {}, ["tv"]),
        ({"/media": ["escape", "tv"]}, {"/media/escape": "/etc"}, ["tv"]),
        ({"/media": ["shared"]}, {"/media/shared": "/library/shared"}, ["shared"]),
        ({"/media": []}, {}, []),
    ],
    ids=["sorted", "hidden", "protected", "symlink-escape", "symlink-inside-roots", "empty"],
)
def test_folders_lists_only_allowed_folders(
    folders: dict[str, list[str]], symlinks: dict[str, str], expected: list[str]
) -> None:
    service, _ = make_service(folders, symlinks)
    listing = service.folders("/media")
    assert listing.path == "/media"
    assert listing.folders == [Folder(name, f"/media/{name}") for name in expected]


@pytest.mark.parametrize(
    ("path", "listed_as", "parent"),
    [
        ("/media", "/media", None),
        ("/media/tv", "/media/tv", "/media"),
        ("/media/tv/../tv/", "/media/tv", "/media"),
        ("/library/a/b", "/library/a/b", "/library/a"),
    ],
)
def test_folders_reports_normalized_path_and_parent_within_roots(
    path: str, listed_as: str, parent: str | None
) -> None:
    service, _ = make_service({listed_as: []})
    listing = service.folders(path)
    assert (listing.path, listing.parent) == (listed_as, parent)


@pytest.mark.parametrize(
    ("path", "symlinks", "error", "code"),
    [
        ("media", {}, InvalidInputError, "invalid_path"),
        ("/etc", {}, InvalidInputError, "destination_not_allowed"),
        ("/media/../etc", {}, InvalidInputError, "destination_not_allowed"),
        ("/media/data", {}, InvalidInputError, "destination_not_allowed"),
        ("/media/link", {"/media/link": "/etc"}, InvalidInputError, "destination_not_allowed"),
        ("/media/missing", {}, NotFoundError, "folder_not_found"),
    ],
)
def test_folders_rejects_paths_outside_roots_or_missing(
    path: str, symlinks: dict[str, str], error: type[Exception], code: str
) -> None:
    service, _ = make_service({"/etc": ["secrets"]}, symlinks)
    with pytest.raises(error) as raised:
        service.folders(path)
    assert raised.value.code == code


@pytest.mark.parametrize(
    ("failure", "error", "code"),
    [
        (NotADirectoryError("a file"), NotFoundError, "folder_not_found"),
        (PermissionError("permission denied"), InvalidInputError, "filesystem_error"),
    ],
)
def test_folders_maps_filesystem_errors(
    failure: OSError, error: type[Exception], code: str
) -> None:
    service, files = make_service({"/media": []})
    files.fail_on["list_folders"] = failure
    with pytest.raises(error) as raised:
        service.folders("/media")
    assert raised.value.code == code
