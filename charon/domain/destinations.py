"""Which directories rules are allowed to move files into. Pure path logic, no I/O."""

import posixpath
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath


def normalize(path: str | PurePath) -> PurePosixPath:
    """Collapse `.`, `..` and duplicate slashes lexically, so `..` can't escape a root."""
    return PurePosixPath(posixpath.normpath(str(path)))


def is_within(path: PurePosixPath, base: PurePosixPath) -> bool:
    return path == base or base in path.parents


@dataclass(frozen=True)
class DestinationPolicy:
    """Destinations must sit inside an allowed root and outside every protected directory.

    Protected directories (e.g. the database's) win over roots, so a root that is too
    broad (such as `/`) still cannot reach them.
    """

    roots: tuple[PurePosixPath, ...]
    protected: tuple[PurePosixPath, ...] = ()

    @classmethod
    def of(
        cls, roots: Iterable[str | PurePath], protected: Iterable[str | PurePath] = ()
    ) -> "DestinationPolicy":
        return cls(tuple(map(normalize, roots)), tuple(map(normalize, protected)))

    def violation(self, destination: str | PurePath) -> str | None:
        """Why `destination` is not allowed, or None if it is."""
        path = normalize(destination)
        if any(is_within(path, p) for p in self.protected):
            return f"{path} is inside a protected directory"
        if not self.roots:
            return "no destination roots are configured (set CHARON_RULE_ROOTS)"
        if not any(is_within(path, r) for r in self.roots):
            allowed = ", ".join(map(str, self.roots))
            return f"{path} is outside the allowed destination roots: {allowed}"
        return None
