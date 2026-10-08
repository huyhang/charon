from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """All settings are read from CHARON_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="CHARON_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    admin_api_key: SecretStr | None = None
    # Comma-separated browser origins allowed to call the API, e.g. a UI dev server.
    cors_origins: Annotated[list[str], NoDecode] = []
    # Directory with a built single-page UI to serve at /. Unset = API only.
    ui_dir: Path | None = None
    # Comma-separated directories rules may move files into. Empty = no destinations allowed.
    rule_roots: Annotated[list[Path], NoDecode] = []

    db_path: Path = Path("/data/charon.db")
    download_dir: Path = Path("/downloads")
    poll_interval_seconds: float = 10.0
    # How often to look for feeds due a refresh; each feed has its own refresh interval.
    feed_poll_interval_seconds: float = 60.0
    feed_timeout_seconds: float = 20.0
    feed_max_bytes: int = 5 * 1024 * 1024

    downloader: Literal["download_station"] = "download_station"
    ds_url: str = "http://localhost:5000"
    ds_username: str = ""
    ds_password: SecretStr = SecretStr("")
    ds_destination: str = "downloads"
    ds_verify_tls: bool = True
    ds_timeout_seconds: float = 15.0

    # TMDB's API Read Access Token, for looking up canonical titles. Optional: admins can save
    # one in Settings instead, which takes its place.
    tmdb_token: SecretStr | None = None
    tmdb_url: str = "https://api.themoviedb.org"
    # The language titles are looked up in: a language code, optionally with a country.
    tmdb_language: str = Field(default="en-US", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    tmdb_timeout_seconds: float = 10.0

    @field_validator("admin_api_key", "tmdb_token", mode="before")
    @classmethod
    def _blank_secret_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("cors_origins", "rule_roots", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("rule_roots")
    @classmethod
    def _roots_are_absolute(cls, roots: list[Path]) -> list[Path]:
        relative = [str(r) for r in roots if not r.is_absolute()]
        if relative:
            raise ValueError(f"rule roots must be absolute paths: {', '.join(relative)}")
        return roots
