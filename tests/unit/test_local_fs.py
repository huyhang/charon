from pathlib import PurePosixPath

import pytest

from charon.adapters.local_fs import LocalFileOps


@pytest.mark.parametrize("is_dir", [False, True])
def test_move_creates_parents_and_moves(tmp_path, is_dir: bool) -> None:
    source = tmp_path / "downloads" / "item"
    if is_dir:
        (source / "sub").mkdir(parents=True)
        (source / "sub" / "file.txt").write_text("x")
    else:
        source.parent.mkdir()
        source.write_text("x")
    destination = tmp_path / "library" / "deep" / "renamed"
    files = LocalFileOps()

    files.move(PurePosixPath(source), PurePosixPath(destination))

    assert not files.exists(PurePosixPath(source))
    assert files.exists(PurePosixPath(destination))
    assert (destination / "sub" / "file.txt").exists() is is_dir


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("file", True),
        ("dir", True),
        ("link to file", True),
        ("link to missing target", True),
        ("nothing", False),
    ],
)
def test_exists_counts_anything_at_the_path_including_broken_symlinks(
    tmp_path, entry: str, expected: bool
) -> None:
    path = tmp_path / "entry"
    if entry == "file":
        path.write_text("x")
    elif entry == "dir":
        path.mkdir()
    elif entry == "link to file":
        (tmp_path / "target").write_text("x")
        path.symlink_to(tmp_path / "target")
    elif entry == "link to missing target":
        path.symlink_to(tmp_path / "missing")
    assert LocalFileOps().exists(PurePosixPath(path)) is expected


def test_resolve_follows_symlinks_and_keeps_missing_parts(tmp_path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    resolved = LocalFileOps().resolve(PurePosixPath(tmp_path / "link" / "new" / "dir"))
    assert resolved == PurePosixPath(real.resolve() / "new" / "dir")
