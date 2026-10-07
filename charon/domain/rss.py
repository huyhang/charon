"""Reads RSS feeds whose items link to magnets. Pure parsing, no I/O."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime

from charon.domain.magnets import (
    display_name,
    exact_length,
    info_hash,
    is_magnet,
    normalize_magnet,
    parse_count,
)
from charon.domain.times import to_utc

# Entity declarations are how "billion laughs" style documents blow up; feeds never need them.
_ENTITY_DECLARATIONS = (
    b"<!ENTITY",
    "<!ENTITY".encode("utf-16-le"),
    "<!ENTITY".encode("utf-16-be"),
)
_SIZE = re.compile(r"^\s*([\d.]+)\s*([KMGT]?i?B)\s*$", re.IGNORECASE)
_UNITS = {
    "b": 1,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "tb": 1000**4,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}


class NotRssError(ValueError):
    """The document isn't an RSS feed Charon can read."""


@dataclass(frozen=True)
class ParsedItem:
    info_hash: str
    magnet: str
    title: str
    # What rules will see: the magnet's name, which is usually the download's name.
    name: str
    published_at: datetime | None
    size_bytes: int | None


@dataclass(frozen=True)
class ParsedFeed:
    title: str | None
    items: list[ParsedItem]
    # Items without a usable magnet link (e.g. links to .torrent files).
    skipped: int


def parse_feed(document: bytes) -> ParsedFeed:
    root = _parse_xml(document)
    if _local(root.tag) not in ("rss", "RDF"):
        raise NotRssError(f"expected an RSS document, found <{_local(root.tag)}>")
    elements = [e for e in root.iter() if _local(e.tag) == "item"]
    parsed = [_item(e) for e in elements]
    items = [item for item in parsed if item is not None]
    return ParsedFeed(title=_channel_title(root), items=items, skipped=len(parsed) - len(items))


def parse_size(text: str) -> int | None:
    """Bytes in a human size such as "1.4 GiB" or "700 MB"."""
    match = _SIZE.match(text)
    if match is None:
        return None
    try:
        return int(float(match[1]) * _UNITS[match[2].lower()])
    except ValueError:
        return None


def parse_date(text: str) -> datetime | None:
    """An RSS (RFC 822) or ISO 8601 date in UTC; dates without a zone are taken as UTC.

    None for anything unreadable, including dates that can't be expressed in UTC.
    """
    text = text.strip()
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    try:
        return to_utc(parsed)
    except ValueError:
        return None


def _parse_xml(document: bytes) -> ET.Element:
    if any(marker in document for marker in _ENTITY_DECLARATIONS):
        raise NotRssError("the document declares XML entities, which feeds never need")
    try:
        return ET.fromstring(document)
    except ET.ParseError as exc:
        raise NotRssError(f"not valid XML ({exc})") from exc


def _item(element: ET.Element) -> ParsedItem | None:
    magnet = _magnet(element)
    hash_ = info_hash(magnet) if magnet else None
    if magnet is None or hash_ is None:
        return None
    title = _text(element, "title")
    return ParsedItem(
        info_hash=hash_,
        magnet=normalize_magnet(magnet),
        title=title or display_name(magnet) or hash_,
        name=display_name(magnet) or title or hash_,
        published_at=_published(element),
        size_bytes=_size(element, magnet),
    )


def _magnet(element: ET.Element) -> str | None:
    """The first magnet among the link, the enclosure and the guid."""
    enclosure = _child(element, "enclosure")
    candidates = [
        _text(element, "link"),
        enclosure.get("url", "") if enclosure is not None else "",
        _text(element, "guid"),
    ]
    return next((c for c in candidates if is_magnet(c)), None)


def _published(element: ET.Element) -> datetime | None:
    for name in ("pubDate", "date", "published", "updated"):
        text = _text(element, name)
        if text and (date := parse_date(text)) is not None:
            return date
    return None


def _size(element: ET.Element, magnet: str) -> int | None:
    enclosure = _child(element, "enclosure")
    length = parse_count(enclosure.get("length", "")) if enclosure is not None else None
    return length or exact_length(magnet) or parse_size(_text(element, "size"))


def _channel_title(root: ET.Element) -> str | None:
    channel = next((e for e in root if _local(e.tag) == "channel"), None)
    return (_text(channel, "title") or None) if channel is not None else None


def _child(element: ET.Element, name: str) -> ET.Element | None:
    """The first direct child with this local name, whatever its namespace."""
    return next((c for c in element if _local(c.tag) == name), None)


def _text(element: ET.Element, name: str) -> str:
    child = _child(element, name)
    return (child.text or "").strip() if child is not None else ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
