"""Keys and the escaping they need.

Result tokens forbid whitespace and harness case names are free text, so
native names are percent-encoded into tokens and kept verbatim in
`provenance.native_id` (worker-prototype.md, G11).
"""

from __future__ import annotations

import uuid
from urllib.parse import quote


def new_attempt_key() -> str:
    """One concrete execution of one workload variant. A retry gets a new key."""
    return f"urn:uuid:{uuid.uuid4()}"


def ingest_key(attempt_key: str, quantity: str) -> str:
    """Producer-scoped idempotency key: unique per variant, quantity, attempt."""
    return f"{attempt_key}/{quantity}"


def to_token(value: str) -> str:
    """Percent-encode whitespace (and percent itself) so `value` is a token."""
    out = value.replace("%", "%25")
    for char in " \t\n\r\f\v":
        out = out.replace(char, f"%{ord(char):02X}")
    return out


def to_filename(key: str) -> str:
    """Percent-encode a key for use as a file name."""
    return quote(key, safe="")
