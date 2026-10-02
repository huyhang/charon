"""Pure helpers for generating and hashing API keys."""

import hashlib
import secrets

KEY_PREFIX = "chk_"
DISPLAY_PREFIX_LENGTH = 12


def generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    # Keys are 256-bit random tokens, so a fast unsalted hash is sufficient.
    return hashlib.sha256(key.encode()).hexdigest()


def display_prefix(key: str) -> str:
    """The non-secret leading part shown in listings to identify a key."""
    return key[:DISPLAY_PREFIX_LENGTH]
