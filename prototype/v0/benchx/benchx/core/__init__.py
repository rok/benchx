"""Core library: read, schema-check, and rule-check benchx documents.

Every stage raises a `DocumentError` at the first problem, so `inspect` reads
top to bottom:

    loader.read → validation.find_schema → validation.check → rules.check

The caller states which kind of document it expects, since it always knows:
`bx validate` is told, `bx ingest` reads results. Rules run last, once the
structural check has passed, since they rely on structure.
"""

from pathlib import Path
from typing import Any

from . import loader, rules, validation


def inspect(path: Path, kind: str) -> dict[str, Any]:
    """Return the file's document, or raise the first `DocumentError` found in it."""
    data = loader.read(path)
    validator = validation.find_schema(data, kind)
    validation.check(data, validator)
    rules.check(data, kind)
    return data
