"""Port for filesystem operations used by post-processing."""

from pathlib import PurePosixPath
from typing import Protocol


class FileOps(Protocol):
    def exists(self, path: PurePosixPath) -> bool:
        """Whether anything is at `path`, including a symlink whose target is missing.

        A broken symlink must count: moving onto it across filesystems would write
        through it to wherever it points.
        """
        ...

    def move(self, source: PurePosixPath, destination: PurePosixPath) -> None:
        """Move a file or directory, creating missing parent directories."""
        ...

    def resolve(self, path: PurePosixPath) -> PurePosixPath:
        """The real path with symlinks followed; missing components are kept as-is."""
        ...

    def list_folders(self, path: PurePosixPath) -> list[str]:
        """Sorted names of the directories directly inside `path`, symlinks followed.

        Raises FileNotFoundError or NotADirectoryError if `path` is not a directory.
        """
        ...
