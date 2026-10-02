import pytest

from charon.bootstrap import build_destination_policy
from charon.config import Settings


@pytest.mark.parametrize(
    ("ui", "destination", "allowed"),
    [
        (False, "media/tv", True),
        (False, "data", False),
        (False, "data/sub", False),
        (True, "ui", False),
        (True, "other", True),
    ],
)
def test_policy_protects_charon_directories_even_under_a_broad_root(
    tmp_path, ui: bool, destination: str, allowed: bool
) -> None:
    settings = Settings(
        _env_file=None,
        rule_roots=[tmp_path],
        db_path=tmp_path / "data" / "charon.db",
        ui_dir=tmp_path / "ui" if ui else None,
    )
    policy = build_destination_policy(settings)
    assert (policy.violation(tmp_path.resolve() / destination) is None) is allowed


@pytest.mark.parametrize(
    ("destination", "problem"),
    [
        ("real/tv", None),  # what the move-time check sees after resolving symlinks
        ("link/tv", None),  # what a client writes when the root is configured via the link
        ("link/data/sub", "protected"),  # Charon's data directory, written via the link
        ("real/data/sub", "protected"),
        ("elsewhere", "outside"),
    ],
)
def test_policy_accepts_paths_as_configured_and_resolved(
    tmp_path, destination: str, problem: str | None
) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    settings = Settings(
        _env_file=None,
        rule_roots=[tmp_path / "link"],
        db_path=tmp_path / "link" / "data" / "charon.db",
    )
    policy = build_destination_policy(settings)
    base = tmp_path if destination.startswith("link") else tmp_path.resolve()
    violation = policy.violation(base / destination)
    assert (violation is None) if problem is None else (problem in violation)
