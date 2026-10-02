import pytest
from pydantic import ValidationError

from charon.config import Settings


@pytest.mark.parametrize(("raw", "expected"), [("", None), ("secret", "secret")])
def test_admin_api_key_from_env(monkeypatch, raw: str, expected: str | None) -> None:
    monkeypatch.setenv("CHARON_ADMIN_API_KEY", raw)
    key = Settings(_env_file=None).admin_api_key
    assert (key.get_secret_value() if key else None) == expected


def test_defaults_target_container_paths() -> None:
    settings = Settings(_env_file=None)
    assert (str(settings.db_path), str(settings.download_dir)) == ("/data/charon.db", "/downloads")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", []),
        ("http://localhost:5173", ["http://localhost:5173"]),
        ("http://a.lan, http://b.lan:8080 ,", ["http://a.lan", "http://b.lan:8080"]),
    ],
)
def test_cors_origins_are_comma_separated(monkeypatch, raw: str, expected: list[str]) -> None:
    monkeypatch.setenv("CHARON_CORS_ORIGINS", raw)
    assert Settings(_env_file=None).cors_origins == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", []), ("/media", ["/media"]), ("/media, /video/tv", ["/media", "/video/tv"])],
)
def test_rule_roots_are_comma_separated(monkeypatch, raw: str, expected: list[str]) -> None:
    monkeypatch.setenv("CHARON_RULE_ROOTS", raw)
    assert [str(r) for r in Settings(_env_file=None).rule_roots] == expected


def test_rule_roots_must_be_absolute(monkeypatch) -> None:
    monkeypatch.setenv("CHARON_RULE_ROOTS", "/media,relative/dir")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
