"""Canonical JSON (RFC 8785) and the hashes built on it."""

import hashlib

import rfc8785


def canonical(value) -> bytes:
    return rfc8785.dumps(value)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def order_ref(order: dict) -> str:
    """#35 §5: the reference a result carries to the order that produced it."""
    return "sha256:" + sha256_hex(canonical(order))
