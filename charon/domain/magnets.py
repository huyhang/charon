"""Pure helpers for reading magnet links."""

import base64
import binascii
import string
from urllib.parse import parse_qs

MAGNET_PREFIX = "magnet:?"
_BTIH = "urn:btih:"


def is_magnet(text: str) -> bool:
    return text.lower().startswith(MAGNET_PREFIX)


def normalize_magnet(text: str) -> str:
    """The magnet with its scheme in lower case (`MAGNET:?…` becomes `magnet:?…`)."""
    return MAGNET_PREFIX + text[len(MAGNET_PREFIX) :] if is_magnet(text) else text


def parse_count(text: str) -> int | None:
    """A whole number written in ASCII digits, else None ("²".isdigit() is True, for one)."""
    return int(text) if text.isascii() and text.isdigit() else None


def info_hash(magnet: str) -> str | None:
    """The BitTorrent info hash as 40 lowercase hex digits, from a hex or base32 `xt`.

    Two magnets for the same torrent have the same info hash, whatever else differs.
    """
    for topic in _params(magnet).get("xt", []):
        if topic.lower().startswith(_BTIH):
            return _normalize_hash(topic[len(_BTIH) :])
    return None


def display_name(magnet: str) -> str | None:
    """The name (`dn`) a magnet advertises, which is usually the torrent's name."""
    names = _params(magnet).get("dn", [""])
    return names[0].strip() or None


def exact_length(magnet: str) -> int | None:
    """The size in bytes (`xl`) a magnet advertises, if any."""
    lengths = _params(magnet).get("xl", [])
    return parse_count(lengths[0]) if lengths else None


def _params(magnet: str) -> dict[str, list[str]]:
    if not is_magnet(magnet):
        return {}
    return parse_qs(magnet[len(MAGNET_PREFIX) :])


def _normalize_hash(value: str) -> str | None:
    if len(value) == 40 and all(c in string.hexdigits for c in value):
        return value.lower()
    if len(value) == 32:
        try:
            return base64.b32decode(value.upper()).hex()
        except binascii.Error:
            return None
    return None
