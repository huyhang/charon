"""Lets clients browse the folders rules may move files into."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath

from charon.domain.destinations import DestinationPolicy, normalize
from charon.errors import InvalidInputError, NotFoundError
from charon.ports.files import FileOps


@dataclass(frozen=True)
class Folder:
    name: str
    path: str


@dataclass(frozen=True)
class FolderListing:
    path: str
    # None when going up would leave the allowed roots.
    parent: str | None
    folders: list[Folder]


class DestinationService:
    """Lists folder names only, never files, and only where a rule could move files.

    Every path is checked both as written and with symlinks resolved, like a real
    move, so a symlink cannot be used to peek outside the allowed roots. Hidden
    folders are left out.
    """

    def __init__(
        self, roots: Iterable[str | PurePath], policy: DestinationPolicy, files: FileOps
    ) -> None:
        self._roots = list(dict.fromkeys(map(normalize, roots)))
        self._policy = policy
        self._files = files

    def roots(self) -> list[str]:
        return [str(root) for root in self._roots if self._allowed(root)]

    def folders(self, path: str) -> FolderListing:
        target = self._checked(path)
        names = self._list(target)
        folders = [
            Folder(name, str(target / name))
            for name in names
            if not name.startswith(".") and self._allowed(target / name)
        ]
        return FolderListing(str(target), self._parent(target), folders)

    def _checked(self, path: str) -> PurePosixPath:
        if not PurePosixPath(path).is_absolute():
            raise InvalidInputError("invalid_path", f"{path!r} is not an absolute path")
        target = normalize(path)
        problem = self._policy.violation(target) or self._policy.violation(
            self._files.resolve(target)
        )
        if problem is not None:
            raise InvalidInputError("destination_not_allowed", problem)
        return target

    def _list(self, target: PurePosixPath) -> list[str]:
        try:
            return self._files.list_folders(target)
        except (FileNotFoundError, NotADirectoryError) as exc:
            raise NotFoundError("folder_not_found", f"{target} is not a folder") from exc
        except OSError as exc:
            raise InvalidInputError("filesystem_error", str(exc)) from exc

    def _parent(self, path: PurePosixPath) -> str | None:
        if path.parent == path or not self._allowed(path.parent):
            return None
        return str(path.parent)

    def _allowed(self, path: PurePosixPath) -> bool:
        return (
            self._policy.violation(path) is None
            and self._policy.violation(self._files.resolve(path)) is None
        )
